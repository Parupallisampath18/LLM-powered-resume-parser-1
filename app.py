from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import os
import json
from datetime import datetime
import logging
from resume_parser.parser import parse_resume, get_all_skills, format_parsed_data, get_degree_graduation_years

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PARSED_DATA'] = 'parsed_data'
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PARSED_DATA'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        
        if not allowed_file(file.filename):
            flash('Invalid file type. Please upload a PDF, DOCX, or image file.', 'error')
            return redirect(request.url)
        
        try:
            # Generate a timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{file.filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Save the uploaded file
            file.save(file_path)
            logger.info(f"File saved: {file_path}")
            
            # Parse the resume
            parsed_data = parse_resume(file_path, use_llm=True)
            
            # Format the parsed data for better display
            formatted_data = format_parsed_data(parsed_data)
            
            # Generate JSON filename and save parsed data
            json_filename = f"{timestamp}_{os.path.splitext(file.filename)[0]}.json"
            json_path = os.path.join(app.config['PARSED_DATA'], json_filename)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'filename': file.filename,
                    'parsed_data': formatted_data,
                    'raw_parsed_data': parsed_data  # Keep the original data for reference
                }, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Parsed data saved: {json_path}")
            
            # Redirect to results page
            return redirect(url_for('results', filename=json_filename))
            
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            flash(f"Error processing file: {str(e)}", 'error')
            return redirect(request.url)

@app.route('/results')
def results():
    filename = request.args.get('filename')
    if not filename:
        flash('No filename provided', 'error')
        return redirect(url_for('index'))
    
    json_path = os.path.join(app.config['PARSED_DATA'], filename)
    
    if not os.path.exists(json_path):
        flash('File not found', 'error')
        return redirect(url_for('index'))
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return render_template('results.html', 
                              filename=data['filename'], 
                              skills=data['parsed_data'].get('skills', []),
                              education=data['parsed_data'].get('education', []),
                              experience=data['parsed_data'].get('experience', []),
                              degree_info=data['parsed_data'].get('degree_info', {}))
    except Exception as e:
        logger.error(f"Error loading results: {str(e)}")
        flash(f"Error loading results: {str(e)}", 'error')
        return redirect(url_for('index'))

@app.route('/filter', methods=['GET'])
def filter_page():
    all_skills = set()
    all_parsed_resumes = []
    
    # Load all parsed resumes
    try:
        for filename in os.listdir(app.config['PARSED_DATA']):
            if filename.endswith('.json'):
                with open(os.path.join(app.config['PARSED_DATA'], filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    resume_skills = data['parsed_data'].get('skills', [])
                    all_skills.update(resume_skills)
                    all_parsed_resumes.append(data['raw_parsed_data'])
    except Exception as e:
        logger.error(f"Error loading skills and resumes: {str(e)}")
        flash(f"Error loading skills and resumes: {str(e)}", 'error')
    
    # Get only degree graduation years
    degree_graduation_years = get_degree_graduation_years(all_parsed_resumes)
    
    predefined_skills = get_all_skills()
    
    combined_skills = []
    for skill in predefined_skills:
        if skill in all_skills:
            combined_skills.append(skill)
            all_skills.remove(skill)
    
    combined_skills.extend(sorted(all_skills))
    
    # Get current year for the template
    current_year = datetime.now().year
    
    # Generate a comprehensive list of years
    all_years = []
    for year in range(1980, current_year + 6):
        all_years.append(year)
    
    return render_template('filter.html', 
                          all_skills=combined_skills, 
                          graduation_years=degree_graduation_years,
                          current_year=current_year,
                          all_years=all_years)

@app.route('/api/filter_resumes', methods=['POST'])
def filter_resumes():
    skills = request.json.get('skills', [])
    selected_year = request.json.get('year', '')
    
    # Handle GPA filtering with proper type conversion and error handling
    gpa_threshold = 0.0  # Default to 0.0 (no filtering)
    try:
        gpa_value = request.json.get('degreeGpa', 0)  # Use degreeGpa instead of gpa
        if gpa_value:
            gpa_threshold = float(gpa_value)
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing GPA value: {str(e)}")
        gpa_threshold = 0.0  # Default to no filtering on error
    
    logger.info(f"Filtering resumes with skills: {skills}, year: {selected_year}, degreeGpa: {gpa_threshold}")
    
    filtered_resumes = []
    try:
        for filename in os.listdir(app.config['PARSED_DATA']):
            if filename.endswith('.json'):
                with open(os.path.join(app.config['PARSED_DATA'], filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    resume_skills = data['parsed_data'].get('skills', [])
                    
                    # Check if skills match (case-insensitive)
                    skills_match = True
                    if skills:
                        skills_match = all(
                            any(s.lower() == skill.lower() for s in resume_skills) 
                            for skill in skills
                        )
                    
                    # Get degree-specific information - try all possible sources
                    degree_year = None
                    degree_gpa = None
                    
                    # First try raw_parsed_data direct fields
                    raw_data = data.get('raw_parsed_data', {})
                    if raw_data.get('degree_graduation_year'):
                        degree_year = raw_data.get('degree_graduation_year')
                    
                    if raw_data.get('degree_gpa'):
                        degree_gpa = raw_data.get('degree_gpa')
                    
                    # If not found, try degree_education
                    if degree_year is None and 'degree_education' in raw_data:
                        degree_year = raw_data['degree_education'].get('graduation_year')
                    
                    if degree_gpa is None and 'degree_education' in raw_data:
                        degree_gpa = raw_data['degree_education'].get('gpa')
                    
                    # If still not found, try formatted degree_info
                    if degree_year is None or degree_gpa is None:
                        degree_info = data['parsed_data'].get('degree_info', {})
                        if degree_info:
                            if degree_year is None:
                                degree_year = degree_info.get('graduation_year')
                            if degree_gpa is None:
                                degree_gpa = degree_info.get('degree_gpa')
                    
                    # Check if year matches (only for degree/B.Tech)
                    year_match = True
                    if selected_year and degree_year:
                        # Convert to string for consistent comparison
                        degree_year_str = str(degree_year)
                        year_match = degree_year_str == str(selected_year)
                    
                    # Check if GPA matches (only for degree/B.Tech)
                    gpa_match = True
                    if gpa_threshold > 0 and degree_gpa is not None:
                        try:
                            degree_gpa_float = float(degree_gpa)
                            gpa_match = degree_gpa_float >= gpa_threshold
                        except (ValueError, TypeError):
                            # If GPA can't be converted to float, it doesn't match
                            gpa_match = False
                    
                    # All filters must match
                    if skills_match and year_match and gpa_match:
                        filtered_resumes.append({
                            'id': filename,
                            'name': data['filename'],
                            'skills': resume_skills,
                            'degree_info': {
                                'year': degree_year,
                                'gpa': degree_gpa
                            },
                            'experience_count': len(data['parsed_data'].get('experience', []))
                        })
    except Exception as e:
        logger.error(f"Error filtering resumes: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    logger.info(f"Found {len(filtered_resumes)} matching resumes")
    return jsonify(filtered_resumes)

@app.route('/api/skills')
def get_skills_api():
    return jsonify(get_all_skills())

@app.route('/api/years')
def get_years_api():
    """API endpoint to get all available graduation years."""
    try:
        all_parsed_resumes = []
        
        # Load all parsed resumes
        for filename in os.listdir(app.config['PARSED_DATA']):
            if filename.endswith('.json'):
                with open(os.path.join(app.config['PARSED_DATA'], filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_parsed_resumes.append(data['raw_parsed_data'])
        
        # Get only degree graduation years
        degree_graduation_years = get_degree_graduation_years(all_parsed_resumes)
        
        return jsonify(degree_graduation_years)
    except Exception as e:
        logger.error(f"Error getting years: {str(e)}")
        return jsonify({'error': str(e)}), 500

def allowed_file(filename):
    """Check if the uploaded file is a PDF, DOCX, or image."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'docx', 'png', 'jpg', 'jpeg'}

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File too large. Maximum file size is 16MB.', 'error')
    return redirect(url_for('index')), 413

@app.errorhandler(500)
def internal_server_error(error):
    logger.error(f"Internal server error: {str(error)}")
    flash('An unexpected error occurred. Please try again later.', 'error')
    return redirect(url_for('index')), 500

if __name__ == '__main__':
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    app.run(debug=True)
