"""
ResumeScope - AI-Based Resume Screening and Job Role Recommendation System
Flask Application & RESTful API Endpoints

Adheres strictly to the AIML Project Proposal specification:
- Text extraction for PDF and DOCX
- PII masking privacy safeguards
- Skill extraction and curated synonym dictionary
- Sentence-BERT (all-MiniLM-L6-v2) semantic similarity
- Hybrid Score = 0.60 * Skill-Match Score + 0.40 * Semantic-Similarity Score
- Top-3 job role recommendations with full explainability reports
- Baseline comparisons (Keyword Overlap, TF-IDF, Sentence-BERT alone, Hybrid)
- Fairness sensitivity check and SQLite history management
"""

import os
import json
from flask import Flask, render_template, request, jsonify, redirect
from werkzeug.utils import secure_filename
# Added authentication utilities
from flask import make_response, g
from backend.security import create_auth_token, verify_auth_token, hash_password, verify_password, encrypt_data, decrypt_data, email_hmac
import datetime

def get_current_user():
    """Retrieve current user from auth token cookie. Returns dict with id, username, email or None."""
    token = request.cookies.get('auth_token')
    if not token:
        return None
    payload = verify_auth_token(token)
    if not payload:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, username, email_encrypted FROM users WHERE id = ?', (payload['user_id'],))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    email = decrypt_data(row['email_encrypted'])
    return {'id': row['id'], 'username': row['username'], 'email': email}

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

from backend.database import (
    init_db,
    get_all_jobs,
    save_analysis_record,
    get_history_records,
    get_history_record_by_id,
    delete_history_record,
    clear_all_history,
    add_job,
    search_jobs,
    get_db_connection
)
from backend.text_extractor import extract_text, clean_text
from backend.pii_masker import mask_pii
from backend.skill_extractor import SkillExtractor
from backend.learning_resources import get_learning_resources
from backend.semantic_matcher import SemanticMatcher
from backend.hybrid_matcher import HybridMatcher
from backend.fairness import FairnessSensitivityChecker
from backend.baselines import run_benchmark_comparison
from backend.data_loader import get_benchmark_test_dataset

app = Flask(__name__)
app.config['SECRET_KEY'] = 'resumescope-secret-key-2025'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Database Schema & Pre-seed benchmark jobs
init_db()

# Lazy-loaded singleton components for fast startup
_skill_extractor = None
_semantic_matcher = None
_hybrid_matcher = None
_fairness_checker = None


def get_skill_extractor() -> SkillExtractor:
    global _skill_extractor
    if _skill_extractor is None:
        _skill_extractor = SkillExtractor()
    return _skill_extractor


def get_semantic_matcher() -> SemanticMatcher:
    global _semantic_matcher
    if _semantic_matcher is None:
        _semantic_matcher = SemanticMatcher()
    return _semantic_matcher


def get_hybrid_matcher() -> HybridMatcher:
    global _hybrid_matcher
    if _hybrid_matcher is None:
        extractor = get_skill_extractor()
        matcher = get_semantic_matcher()
        _hybrid_matcher = HybridMatcher(extractor, matcher)
    return _hybrid_matcher


def get_fairness_checker() -> FairnessSensitivityChecker:
    global _fairness_checker
    if _fairness_checker is None:
        _fairness_checker = FairnessSensitivityChecker(get_hybrid_matcher())
    return _fairness_checker


@app.route('/')
def index():
    """
    Renders the unified single-page dashboard.
    """
    user = get_current_user()
    if not user:
        return redirect('/login')
    return render_template('index.html', user=user)

# Frontend pages for authentication

@app.route('/signup')
def signup_page():
    if get_current_user():
        return redirect('/')
    return render_template('signup.html')

@app.route('/login')
def login_page():
    if get_current_user():
        return redirect('/')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout_page():
    resp = redirect('/login')
    resp.delete_cookie('auth_token', path='/', httponly=True, samesite='Lax')
    return resp

@app.route('/profile')
@login_required
def profile_page():
    user = g.current_user
    return render_template('profile.html', user=user)


# -------- Authentication Endpoints --------

@app.route('/api/signup', methods=['POST'])
def signup():
    # Try standard JSON parsing first
    data = request.get_json(silent=True) or {}
    # Fallback: raw request body may contain JSON
    if not data:
        try:
            import json as _json
            raw = request.get_data(as_text=True)
            data = _json.loads(raw) if raw else {}
        except Exception:
            data = {}
    # Final fallback to form-encoded data
    if not data:
        data = request.form.to_dict()
    required = {'username', 'email', 'password'}
    if not required.issubset(data):
        return jsonify({'success': False, 'error': f"Missing fields: {required - data.keys()}"}), 400
    username = data['username'].strip()
    email = data['email'].strip()
    password = data['password']
    if not username or not email:
        return jsonify({'success': False, 'error': 'Name and email are required'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
    encrypted_email = encrypt_data(email)
    conn = get_db_connection()
    cur = conn.cursor()
    # Compute deterministic HMAC for email lookup
    email_hmac_val = email_hmac(email)
    # Check for duplicate email via HMAC (deterministic)
    cur.execute('SELECT id FROM users WHERE email_hmac = ?', (email_hmac_val,))
    if cur.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Email already registered'}), 409
    cur.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Name is already in use'}), 409
    pw_hash = hash_password(password)
    try:
        cur.execute('INSERT INTO users (username, email_encrypted, password_hash, email_hmac) VALUES (?,?,?,?)',
                    (username, encrypted_email, pw_hash, email_hmac_val))
        conn.commit()
        user_id = cur.lastrowid
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': 'Unable to create account'}), 500
    conn.close()
    return jsonify({'success': True, 'user_id': user_id}), 201

@app.route('/api/login', methods=['POST'])
def login():
    # Try JSON first
    data = request.get_json(silent=True) or {}
    # Fallback raw body JSON
    if not data:
        try:
            import json as _json
            raw = request.get_data(as_text=True)
            data = _json.loads(raw) if raw else {}
        except Exception:
            data = {}
    # Final fallback to form data
    if not data:
        data = request.form.to_dict()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    # Use deterministic HMAC for email lookup instead of encrypted email equality
    email_hmac_val = email_hmac(email)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id, username, password_hash FROM users WHERE email_hmac = ?', (email_hmac_val,))
        row = cur.fetchone()
    except Exception as e:
        # Likely the column does not exist – migration not performed
        conn.close()
        return jsonify({'success': False, 'error': 'Authentication database not migrated: missing email_hmac column'}), 500
    conn.close()
    if not row or not verify_password(password, row['password_hash']):
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    token = create_auth_token(row['id'], row['username'])
    resp = make_response(jsonify({'success': True, 'message': 'Logged in'}))
    resp.set_cookie('auth_token', token, httponly=True, samesite='Lax')
    return resp

@app.route('/api/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify({'success': True, 'message': 'Logged out'}))
    resp.delete_cookie('auth_token', path='/', httponly=True, samesite='Lax')
    return resp

@app.route('/api/profile', methods=['GET', 'PUT'])
@login_required
def profile():
    user = g.current_user
    if request.method == 'GET':
        return jsonify({'success': True, 'profile': {'id': user['id'], 'username': user['username'], 'email': user['email']}})
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict()
    if not data:
        data = request.form.to_dict()
    updates = []
    params = []
    conn = get_db_connection()
    cur = conn.cursor()
    if 'username' in data:
        updates.append('username = ?')
        params.append(data['username'].strip())
    if 'email' in data:
        updates.append('email_encrypted = ?')
        params.append(encrypt_data(data['email'].strip()))
    if 'password' in data:
        curr_pw = data.get('current_password')
        if not curr_pw:
            conn.close()
            return jsonify({'success': False, 'error': 'Current password required'}), 403
        # Verify current password
        cur.execute('SELECT password_hash FROM users WHERE id = ?', (user['id'],))
        row = cur.fetchone()
        if not row or not verify_password(curr_pw, row['password_hash']):
            conn.close()
            return jsonify({'success': False, 'error': 'Current password verification failed'}), 403
        updates.append('password_hash = ?')
        params.append(hash_password(data['password']))
    if not updates:
        conn.close()
        return jsonify({'success': False, 'error': 'No fields to update'}), 400
    params.append(user['id'])
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    try:
        cur.execute(sql, tuple(params))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500
    conn.close()
    return jsonify({'success': True, 'message': 'Profile updated'}), 200


@app.route('/api/jobs', methods=['GET', 'POST'])
def manage_jobs():
    """
    GET: Retrieves all job roles from the SQLite catalog.
    POST: Adds a new job role via JSON payload.
    """
    if request.method == 'GET':
        jobs = get_all_jobs()
        return jsonify({"success": True, "count": len(jobs), "jobs": jobs})

    # POST method
    if not request.is_json:
        return jsonify({"success": False, "error": "JSON body required"}), 400
    data = request.get_json()
    required_fields = {"title", "domain", "description", "required_skills"}
    if not required_fields.issubset(data):
        return jsonify({"success": False, "error": f"Missing fields: {required_fields - data.keys()}"}), 400
    try:
        job_id = add_job(
            title=data["title"],
            domain=data["domain"],
            description=data["description"],
            required_skills=data["required_skills"]
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    return jsonify({"success": True, "job_id": job_id}), 201

@app.route('/api/jobs/search', methods=['GET'])
def search_job():
    """Fallback search for similar job titles when user query is unknown.
    Query param: ?query=some+role
    """
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "error": "Missing query parameter"}), 400
    matches = search_jobs(query)
    return jsonify({"success": True, "count": len(matches), "jobs": matches})



@app.route('/api/analyze', methods=['POST'])
def analyze_resume():
    """
    Analyzes uploaded resume against job descriptions catalog (or uploaded custom JD).
    Executes:
    1. Text extraction (PyMuPDF / python-docx)
    2. PII masking
    3. Skill extraction & synonym normalization
    4. Sentence-BERT dense embeddings & cosine similarity
    5. Hybrid matching & Top-3 ranking
    6. Explainability breakdown
    """
    resume_text = ""
    resume_filename = "Uploaded_Resume"

    # Check for file upload
    if 'resume_file' in request.files:
        file = request.files['resume_file']
        if file.filename != '':
            resume_filename = secure_filename(file.filename)
            file_bytes = file.read()
            resume_text = extract_text(file_bytes, filename=resume_filename)
    elif request.is_json and 'resume_text' in request.json:
        resume_text = clean_text(request.json.get('resume_text', ''))
        resume_filename = request.json.get('resume_name', 'Input_Resume.txt')

    if not resume_text.strip():
        return jsonify({
            "success": False,
            "error": "No resume text or valid PDF/DOCX file provided."
        }), 400

    # Privacy Safeguard: Mask PII before analysis & storage
    masked_text, pii_meta = mask_pii(resume_text)

    # Load Job Descriptions
    jobs = get_all_jobs()
    if not jobs:
        return jsonify({"success": False, "error": "No job descriptions configured in database."}), 500

    # Optional: If user uploaded custom JD (via file or text)
    custom_jd_text = ""
    custom_jd_title = "Custom Target Job"
    if 'jd_file' in request.files and request.files['jd_file'].filename != '':
        jd_file = request.files['jd_file']
        jd_bytes = jd_file.read()
        custom_jd_title = f"Custom Job ({secure_filename(jd_file.filename)})"
        custom_jd_text = extract_text(jd_bytes, filename=secure_filename(jd_file.filename))
    elif 'jd_text' in request.form and request.form['jd_text'].strip():
        custom_jd_text = clean_text(request.form['jd_text'])
    elif request.is_json and 'jd_text' in request.json and request.json['jd_text'].strip():
        custom_jd_text = clean_text(request.json['jd_text'])
        custom_jd_title = request.json.get('jd_name', 'Custom Job')

    if custom_jd_text.strip():
        extractor = get_skill_extractor()
        jd_skills = extractor.extract_skills(custom_jd_text)["normalized_skills"]
        custom_job = {
            "id": 999,
            "title": custom_jd_title,
            "domain": "Custom",
            "description": custom_jd_text[:300] if len(custom_jd_text) > 300 else custom_jd_text,
            "required_skills": jd_skills if jd_skills else ["Communication", "Problem Solving"]
        }
        jobs = [custom_job] + jobs

    # Run Hybrid Matcher & Top-3 Ranking
    hybrid_engine = get_hybrid_matcher()
    ranking_results = hybrid_engine.rank_jobs(masked_text, jobs, top_n=3)

    top_recs = ranking_results["top_recommendations"]
    for recommendation in top_recs:
        recommendation["learning_resources"] = get_learning_resources(
            recommendation.get("skills_not_detected", [])
        )
    top_role_title = top_recs[0]["job_title"] if top_recs else "No Match"
    top_score = top_recs[0]["final_hybrid_score"] if top_recs else 0.0

    # Persist in SQLite Analysis History
    user = get_current_user()
    user_id = user['id'] if user else 1
    record_id = save_analysis_record(
        resume_name=resume_filename,
        top_job_role=top_role_title,
        match_score=top_score,
        details={
            "top_recommendations": top_recs,
            "pii_meta": pii_meta,
            "weights": ranking_results["weights_used"]
        },
        user_id=user_id
    )

    return jsonify({
        "success": True,
        "record_id": record_id,
        "resume_name": resume_filename,
        "overall_top_match": top_score,
        "top_recommendations": top_recs,
        "pii_masking": pii_meta,
        "weights": ranking_results["weights_used"]
    })


@app.route('/api/history', methods=['GET'])
def get_history():
    """
    Returns stored candidate analysis history records from SQLite.
    """
    records = get_history_records()
    return jsonify({"success": True, "count": len(records), "records": records})


@app.route('/api/history/<int:record_id>', methods=['GET'])
def get_single_history_record(record_id):
    """
    Retrieves full details of a single analysis record by ID.
    """
    record = get_history_record_by_id(record_id)
    if not record:
        return jsonify({"success": False, "error": "Record not found"}), 404
    return jsonify({"success": True, "record": record})


@app.route('/api/history/<int:record_id>', methods=['DELETE'])
def delete_history_item(record_id):
    """
    Deletes a single candidate record from history (privacy compliance).
    """
    success = delete_history_record(record_id)
    return jsonify({"success": success})


@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    """
    Clears all analysis history records from SQLite.
    """
    deleted_count = clear_all_history()
    return jsonify({"success": True, "deleted_count": deleted_count})


@app.route('/api/benchmark', methods=['GET'])
def get_benchmark():
    """
    Executes comparison of the 4 methods on the benchmark evaluation dataset:
    1. Keyword Overlap
    2. TF-IDF + Cosine Similarity
    3. Sentence-BERT + Cosine Similarity
    4. Proposed Hybrid Method
    Returns Precision, Recall, F1, and Precision@3 per Section 9.
    """
    benchmark_dataset = get_benchmark_test_dataset()
    jobs = get_all_jobs()
    summary = run_benchmark_comparison(
        test_samples=benchmark_dataset,
        job_catalog=jobs,
        semantic_matcher=get_semantic_matcher(),
        skill_extractor=get_skill_extractor()
    )
    return jsonify({
        "success": True,
        "benchmark_samples_count": len(benchmark_dataset),
        "metrics": summary
    })


@app.route('/api/fairness', methods=['POST'])
def check_fairness():
    """
    Executes the Fairness Sensitivity Check mandated by Section 10:
    Compares score stability before and after adding irrelevant contact details.
    """
    data = request.get_json(silent=True) or {}
    if not data:
        data = request.form.to_dict()
    resume_text = data.get('resume_text', '')

    if not resume_text:
        # If no resume text provided, use standard sample
        resume_text = (
            "Machine Learning Engineer with experience in Python, PyTorch, "
            "Scikit-Learn, Deep Learning, and predictive modeling."
        )

    jobs = get_all_jobs()
    checker = get_fairness_checker()
    report = checker.run_sensitivity_test(resume_text, jobs)

    return jsonify({"success": True, "fairness_report": report})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting ResumeScope Backend on http://127.0.0.1:{port}")
    app.run(host='127.0.0.1', port=port, debug=False)
