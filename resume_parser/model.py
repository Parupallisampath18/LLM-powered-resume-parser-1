import re
import spacy
import time
import json
import anthropic

class ResumeParserModel:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ResumeParserModel, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        # Load spaCy model for better text processing
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
            self.nlp = spacy.load("en_core_web_sm")

        # Anthropic API configuration
        self.api_key = "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"
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-3-7-sonnet-20250219"  # Using Claude model
        
        # Define education level keywords for classification
        self.degree_keywords = [
            "bachelor", "b.tech", "btech", "b. tech", "undergraduate", "ug", "be", "b.e.",
            "engineering", "computer science", "cse", "it", "information technology",
            "electrical", "mechanical", "civil", "electronics", "college"
        ]
        
        self.secondary_keywords = [
            "senior secondary", "12th", "12 th", "xii", "higher secondary", "intermediate",
            "junior college", "pre-university", "hsc", "intermediate", "10+2"
        ]
        
        self.high_school_keywords = [
            "secondary", "high school", "10th", "10 th", "x", "ssc", "matriculation"
        ]
        
        print("Resume parser model initialized successfully!")

    def parse_resume(self, text, use_llm=True):
        """Parse the resume text using both LLM and rule-based approaches."""
        start_time = time.time()
        
        llm_results = None
        if use_llm:
            try:
                llm_results = self._parse_with_anthropic(text)
                print(f"Anthropic AI parsing completed in {time.time() - start_time:.2f} seconds")
            except Exception as e:
                print(f"Error using Anthropic AI: {e}. Falling back to rule-based parsing.")
        
        if not llm_results:
            doc = self.nlp(text)
            skills = self._extract_skills(text, doc)
            education = self._extract_education(text, doc)
            experience = self._extract_experience(text, doc)

            rule_based_results = {
                "skills": skills,
                "education": education,
                "experience": experience
            }
            print(f"Rule-based parsing completed in {time.time() - start_time:.2f} seconds")
            return rule_based_results
        
        return llm_results

    def _parse_with_anthropic(self, text):
        """Parse resume using Anthropic API."""
        system_prompt = """You are a resume parsing expert. Extract the following information from the resume:

1. Skills: Extract a comprehensive list of all technical and soft skills mentioned in the resume.
   Return as a simple list of skill names.

2. Education: Extract all educational qualifications including degree name, institution name, 
   graduation year, GPA, and any relevant details. Format each entry as a dictionary with fields: 
   'institution', 'degree', 'graduation_year', 'gpa', and 'education_level'. 
   
   For education_level, categorize as:
   - 'degree' for Bachelor's degrees, B.Tech, Engineering degrees, College education
   - 'secondary' for Senior Secondary, 12th, Intermediate, 10+2
   - 'high_school' for Secondary, 10th, High School
   
   IMPORTANT: Only set the 'graduation_year' field for degree-level education (B.Tech, Bachelor's, etc.).
   For secondary and high_school levels, use 'completion_year' instead of 'graduation_year'.
   
   For GPA, ensure it's converted to a float value on a 10-point scale. If GPA is missing, set it to null.

3. Experience: Extract all work experiences, internships, and relevant projects including company name, 
   position title, time period, and key responsibilities. Format each entry as a dictionary with fields: 
   'company', 'position', 'date', and 'description'.

Return the information in a valid JSON format with these three main categories: "skills" (array of strings), 
"education" (array of objects), and "experience" (array of objects).
"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": f"Parse the following resume and extract skills, education, and experience:\n\n{text}"}
                ]
            )
            
            content = message.content[0].text
            json_content = self._extract_json_from_text(content)
            
            try:
                parsed_data = json.loads(json_content)
                
                # Process education entries
                if 'education' in parsed_data:
                    for edu in parsed_data['education']:
                        # If education_level is not set, determine it based on degree name
                        if 'education_level' not in edu and 'degree' in edu:
                            edu['education_level'] = self._classify_education_level(edu['degree'])
                        
                        # Ensure GPA is properly formatted as a float or None
                        if 'gpa' in edu and edu['gpa']:
                            try:
                                edu['gpa'] = float(edu['gpa'])
                            except (ValueError, TypeError):
                                edu['gpa'] = None
                        else:
                            edu['gpa'] = None
                        
                        # Fix graduation_year field - only keep for degree level
                        if edu.get('education_level') != 'degree' and 'graduation_year' in edu:
                            # Move to completion_year and remove graduation_year
                            edu['completion_year'] = edu['graduation_year']
                            edu.pop('graduation_year', None)
                
                return {
                    "skills": parsed_data.get('skills', []),
                    "education": parsed_data.get('education', []),
                    "experience": parsed_data.get('experience', [])
                }
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON from Anthropic response: {e}")
                print(f"Raw content: {content}")
                
        except Exception as e:
            print(f"Error with Anthropic API request: {e}")
        
        # Fallback to rule-based parsing
        doc = self.nlp(text)
        return {
            "skills": self._extract_skills(text, doc),
            "education": self._extract_education(text, doc),
            "experience": self._extract_experience(text, doc)
        }
    
    def _classify_education_level(self, degree_text):
        """Classify education level based on degree text."""
        if not degree_text:
            return None
            
        degree_text = degree_text.lower()
        
        # Check for degree level
        for keyword in self.degree_keywords:
            if keyword in degree_text:
                return "degree"
                
        # Check for senior secondary
        for keyword in self.secondary_keywords:
            if keyword in degree_text:
                return "secondary"
                
        # Check for high school
        for keyword in self.high_school_keywords:
            if keyword in degree_text:
                return "high_school"
                
        # Default to degree if contains the word "degree"
        if "degree" in degree_text:
            return "degree"
            
        return None
    
    def _extract_json_from_text(self, text):
        """Extract JSON content from text that might contain markdown or other formatting."""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1)

        json_match = re.search(r'(\{[\s\S]*\})', text)
        if json_match:
            return json_match.group(1)

        return text
    
    def _extract_skills(self, text, doc):
        """Extract all skills from the resume text using rule-based approach."""
        skills = []
        
        technical_skills = [
            "Python", "Java", "JavaScript", "C++", "C#", "Ruby", "PHP", "Swift", "Kotlin", "Go",
            "HTML", "CSS", "React", "Angular", "Vue.js", "Node.js", "Express", "Django", "Flask",
            "jQuery", "Bootstrap", "REST API", "GraphQL", "SQL", "MySQL", "PostgreSQL", "MongoDB",
            "Oracle", "SQLite", "Redis", "AWS", "Azure", "Google Cloud", "Docker", "Kubernetes",
            "Git", "GitHub", "GitLab", "Jenkins", "CI/CD", "TensorFlow", "PyTorch", "Machine Learning",
            "Deep Learning", "AI", "Data Analysis", "Data Science", "NLP", "Computer Vision"
        ]
        
        soft_skills = [
            "Leadership", "Communication", "Teamwork", "Problem-Solving", "Critical Thinking",
            "Time Management", "Project Management", "Creativity", "Adaptability", "Organization",
            "Presentation", "Collaboration", "Analytical", "Detail-Oriented", "Strategic Thinking"
        ]
        
        skills_section_pattern = r'(?:SKILLS|SKILLS & INTERESTS|TECHNICAL SKILLS|PROFESSIONAL SKILLS)[^\n]*\n(.*?)(?:^#|^##|^[A-Z\s]{2,}|\Z)'
        skills_match = re.search(skills_section_pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        
        if skills_match:
            skills_text = skills_match.group(1)
            
            category_skills = re.findall(r'([A-Za-z\s]+):([^•#]+)', skills_text)
            for category, category_skills_text in category_skills:
                for skill in re.split(r',|\n|•', category_skills_text):
                    skill = skill.strip()
                    if skill and len(skill) > 1 and skill not in skills:
                        skills.append(skill)
            
            bullet_skills = re.findall(r'•\s*([^•\n]+)', skills_text)
            for skill in bullet_skills:
                skill = skill.strip()
                if skill and len(skill) > 1 and skill not in skills:
                    skills.append(skill)
        
        text_lower = text.lower()
        for skill in technical_skills + soft_skills:
            skill_lower = skill.lower()
            if re.search(r'\b' + re.escape(skill_lower) + r'\b', text_lower) and skill not in skills:
                skills.append(skill)
        
        return skills

    def _extract_education(self, text, doc):
        """Extract education information from the resume with education level classification."""
        education = []
        
        education_section_pattern = r'(?:EDUCATION|ACADEMIC BACKGROUND)[^\n]*\n(.*?)(?:^#|^##|^[A-Z\s]{2,}|\Z)'
        education_match = re.search(education_section_pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        
        if education_match:
            education_text = education_match.group(1)
            
            # Try to identify separate education entries
            # First, split by blank lines or bullet points
            raw_entries = re.split(r'\n\s*\n|\n•|\n\*|\n-', education_text)
            
            for raw_entry in raw_entries:
                if not raw_entry.strip():
                    continue
                
                # Process each education entry
                lines = [line.strip() for line in raw_entry.split('\n') if line.strip()]
                if not lines:
                    continue
                
                # Initialize entry with default values
                education_entry = {
                    "institution": "",
                    "degree": None,
                    "education_level": None,
                    "gpa": None
                }
                
                # Extract year ranges like 2019-2023
                year_range_match = re.search(r'(\d{4})\s*[-–—]\s*(\d{4}|\d{2}|present|ongoing)', raw_entry, re.IGNORECASE)
                if year_range_match:
                    end_year = year_range_match.group(2)
                    if len(end_year) == 2:  # Convert 2-digit year to 4-digit
                        end_year = '20' + end_year
                    elif end_year.lower() in ['present', 'ongoing']:
                        from datetime import datetime
                        end_year = str(datetime.now().year)
                    
                    # Store the year
                    year = end_year
                else:
                    # Try to find any 4-digit year
                    year_match = re.search(r'(\d{4})', raw_entry)
                    year = year_match.group(1) if year_match else None
                
                # Extract GPA/CGPA
                gpa_match = re.search(r'(?:GPA|CGPA|CPI)[^\d]*([\d\.]+)', raw_entry, re.IGNORECASE)
                if gpa_match:
                    try:
                        education_entry["gpa"] = float(gpa_match.group(1))
                    except (ValueError, TypeError):
                        pass
                
                # Determine institution and degree
                for line in lines:
                    # Skip bullet points that are likely details
                    if line.startswith('•') or line.startswith('*') or line.startswith('-'):
                        continue
                    
                    # Check if this line contains degree information
                    has_degree_keywords = any(keyword in line.lower() for keyword in 
                                             self.degree_keywords + self.secondary_keywords + self.high_school_keywords)
                    
                    if not education_entry["institution"] or has_degree_keywords:
                        education_entry["institution"] = line
                        
                        # Try to extract degree name
                        degree_match = re.search(r'(Bachelor|Master|Diploma|B\.Tech|M\.Tech|Ph\.D|Senior Secondary|Secondary)[^,\n]*', line, re.IGNORECASE)
                        if degree_match:
                            education_entry["degree"] = degree_match.group(0).strip()
                
                # Determine education level
                education_entry["education_level"] = self._classify_education_level(
                    education_entry["degree"] if education_entry["degree"] else education_entry["institution"]
                )
                
                # Only set graduation_year for degree-level education
                if education_entry["education_level"] == "degree" and year:
                    education_entry["graduation_year"] = year
                elif year:
                    education_entry["completion_year"] = year
                
                education.append(education_entry)
            
            # If no entries were found with the above method, try line-by-line parsing
            if not education:
                current_entry = {}
                
                for line in education_text.split('\n'):
                    line = line.strip()
                    if not line:
                        if current_entry:
                            # Determine education level
                            if 'degree' in current_entry:
                                current_entry['education_level'] = self._classify_education_level(current_entry['degree'])
                            else:
                                current_entry['education_level'] = self._classify_education_level(current_entry.get('institution', ''))
                            
                            # Only set graduation_year for degree-level education
                            if current_entry.get('education_level') == 'degree' and 'year' in current_entry:
                                current_entry['graduation_year'] = current_entry.pop('year')
                            elif 'year' in current_entry:
                                current_entry['completion_year'] = current_entry.pop('year')
                            
                            education.append(current_entry)
                            current_entry = {}
                        continue
                    
                    # Extract information from the line
                    degree_match = re.search(r'(Bachelor|Master|Diploma|B\.Tech|M\.Tech|Ph\.D|Senior Secondary|Secondary)[^,\n]*', line, re.IGNORECASE)
                    institution_match = re.search(r'(University|College|Institute|School)[^,\n]*', line, re.IGNORECASE)
                    year_match = re.search(r'(\d{4})', line)
                    gpa_match = re.search(r'(?:GPA|CGPA)[^\d]*([\d\.]+)', line, re.IGNORECASE)
                    
                    if degree_match and 'degree' not in current_entry:
                        current_entry['degree'] = degree_match.group(0).strip()
                    
                    if institution_match and 'institution' not in current_entry:
                        current_entry['institution'] = institution_match.group(0).strip()
                    elif 'institution' not in current_entry:
                        current_entry['institution'] = line
                    
                    if year_match and 'year' not in current_entry:
                        current_entry['year'] = year_match.group(1)
                    
                    if gpa_match and 'gpa' not in current_entry:
                        current_entry['gpa'] = float(gpa_match.group(1))
                
                # Add the last entry if exists
                if current_entry:
                    # Determine education level
                    if 'degree' in current_entry:
                        current_entry['education_level'] = self._classify_education_level(current_entry['degree'])
                    else:
                        current_entry['education_level'] = self._classify_education_level(current_entry.get('institution', ''))
                    
                    # Only set graduation_year for degree-level education
                    if current_entry.get('education_level') == 'degree' and 'year' in current_entry:
                        current_entry['graduation_year'] = current_entry.pop('year')
                    elif 'year' in current_entry:
                        current_entry['completion_year'] = current_entry.pop('year')
                    
                    education.append(current_entry)
        
        return education

    def _extract_experience(self, text, doc):
        """Extract work experience, projects, and internships from the resume."""
        experience = []
        
        sections = [
            ("EXPERIENCE", r'(?:EXPERIENCE|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE)[^\n]*\n(.*?)(?:^#|^##|^[A-Z\s]{2,}|\Z)'),
            ("PROJECTS", r'(?:PROJECTS|PROJECT EXPERIENCE)[^\n]*\n(.*?)(?:^#|^##|^[A-Z\s]{2,}|\Z)'),
            ("INTERNSHIPS", r'(?:INTERNSHIPS|INTERNSHIP EXPERIENCE)[^\n]*\n(.*?)(?:^#|^##|^[A-Z\s]{2,}|\Z)')
        ]
        
        for section_name, pattern in sections:
            section_match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
            
            if section_match:
                section_text = section_match.group(1)
                entries = re.findall(r'([^\n•#]+)(?:•|\*|\-)([^\n•#]+)', section_text)
                for name, description in entries:
                    # Try to extract position and company
                    position_match = re.search(r'([\w\s]+) at ([\w\s]+)', name, re.IGNORECASE)
                    date_match = re.search(r'(\w+ \d{4}\s*-\s*(?:\w+ \d{4}|Present))', name, re.IGNORECASE)
                    
                    if position_match:
                        position = position_match.group(1).strip()
                        company = position_match.group(2).strip()
                    else:
                        position = None
                        company = name.strip()
                    
                    date = date_match.group(1) if date_match else None
                    
                    experience_entry = {
                        "company": company,
                        "position": position,
                        "date": date,
                        "description": description.strip(),
                        "type": section_name.lower()
                    }
                    experience.append(experience_entry)
                
                if not entries:
                    current_entry = {"type": section_name.lower()}
                    for line in section_text.split('\n'):
                        line = line.strip()
                        if not line or line.startswith('#') or line.startswith('##'):
                            continue
                            
                        if re.match(r'^[A-Z]', line) and 'company' in current_entry:  # New entry starts with capital letter
                            experience.append(current_entry)
                            current_entry = {"type": section_name.lower()}
                        
                        if 'company' not in current_entry:
                            # Try to extract position and company
                            position_match = re.search(r'([\w\s]+) at ([\w\s]+)', line, re.IGNORECASE)
                            date_match = re.search(r'(\w+ \d{4}\s*-\s*(?:\w+ \d{4}|Present))', line, re.IGNORECASE)
                            
                            if position_match:
                                current_entry["position"] = position_match.group(1).strip()
                                current_entry["company"] = position_match.group(2).strip()
                            else:
                                current_entry["company"] = line
                            
                            if date_match:
                                current_entry["date"] = date_match.group(1)
                        else:
                            if 'description' not in current_entry:
                                current_entry["description"] = line
                            else:
                                current_entry["description"] += " " + line
                    
                    if 'company' in current_entry:
                        experience.append(current_entry)
        
        return experience

    def get_degree_education(self, parsed_data):
        """Extract only degree/B.Tech level education from parsed data."""
        if not parsed_data or "education" not in parsed_data:
            return None
            
        # First look for entries explicitly marked as degree level
        for edu in parsed_data["education"]:
            if edu.get("education_level") == "degree" and "graduation_year" in edu:
                return edu
                
        # Fallback: try to identify degree by keywords if education_level is not set
        for edu in parsed_data["education"]:
            degree = edu.get("degree", "").lower() if edu.get("degree") else ""
            institution = edu.get("institution", "").lower() if edu.get("institution") else ""
            
            # Check if it contains degree keywords
            if any(keyword in degree or keyword in institution for keyword in self.degree_keywords):
                # Only return if it has a graduation_year (not completion_year)
                if "graduation_year" in edu:
                    return edu
                
        return None
    
    def get_degree_graduation_years(self, parsed_data):
        """Extract only graduation years from degree/B.Tech level education."""
        if not parsed_data or "education" not in parsed_data:
            return []
            
        graduation_years = []
        
        for edu in parsed_data["education"]:
            # Only include graduation_year from degree-level education
            if edu.get("education_level") == "degree" and "graduation_year" in edu:
                graduation_years.append(edu["graduation_year"])
                
        return graduation_years