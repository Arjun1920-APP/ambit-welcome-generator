import os
import textwrap
from flask import Flask, render_template, request
from PIL import Image, ImageDraw, ImageFont, ImageOps
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

load_dotenv()
app = Flask(__name__)

# --- FOLDERS ---
# Base Template Folder
app.config['TEMPLATE_FOLDER'] = 'static/template/'
app.config['TEMPLATE_PATH'] = os.path.join(app.config['TEMPLATE_FOLDER'], 'template.png') 
app.config['LOGO_PATH'] = os.path.join(app.config['TEMPLATE_FOLDER'], 'ambit_logo.png') # Put logo here

# Processing Folders
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['GENERATED_FOLDER'] = 'static/generated'
app.config['FONT_FOLDER'] = 'static/fonts'

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)
os.makedirs(app.config['FONT_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMPLATE_FOLDER'], exist_ok=True)

# --- SMART ALIGNMENT HELPERS ---
def draw_centered_text(draw, text, center_x, y, font, fill_color):
    """Measures the text and draws it perfectly horizontally centered."""
    try:
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
    except AttributeError:
        text_w = font.getsize(text)[0]
        
    x = center_x - (text_w // 2) 
    draw.text((x, y), text, fill=fill_color, font=font)

def draw_centered_wrapped_text(draw, text, center_x, y, max_width, font, fill_color, line_spacing=1.4):
    """Wraps text and centers EACH line individually."""
    lines = []
    words = text.split()
    current_line = ""
    
    # Text Wrapping Logic
    for word in words:
        test_line = current_line + word + " "
        try:
            width = font.getbbox(test_line)[2]
        except AttributeError:
            width = font.getsize(test_line)[0]
            
        if width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        lines.append(current_line.strip())
        
    # Get line height for spacing
    try:
        line_height = int(font.getbbox('Ay')[3] * line_spacing)
    except AttributeError:
        line_height = int(font.getsize('Ay')[1] * line_spacing)
        
    # Draw each line centered
    current_y = y
    for line in lines:
        draw_centered_text(draw, line, center_x, current_y, font, fill_color)
        current_y += line_height
        
    return current_y

# --- AUTO-SCALING IMAGE GENERATOR (Now with LOGO support) ---
def create_welcome_image_auto(data, photo_path, output_path):
    base_image = Image.open(app.config['TEMPLATE_PATH']).convert("RGBA")
    W, H = base_image.size 

    # --- LAYOUT CENTERS (Percentages based on target poster) ---
    photo_diameter = int(W * 0.175)  
    photo_x = int(W * 0.082)         
    photo_y = int(H * 0.115)         

    # Position for Ambit Logo (Top Right Corner)
    logo_w = int(W * 0.22)            # Adjust logo width size here
    logo_right_margin = int(W * -0.01) # Space from right edge
    logo_top_margin = int(H * -0.03)   # Space from top edge

    # Center point of the top grey box
    grey_box_center_x = int(W * 0.66)     
    
    # Adjusted Y-coordinates to fit 4 lines instead of 3
    name_y = int(H * 0.16)
    role_y = int(H * 0.23)
    biz_y = int(H * 0.28)
    loc_y = int(H * 0.33) # New Y-coordinate for location

    # Center point of the bottom welcome box (Exactly 50% of screen width)
    welcome_box_center_x = int(W * 0.50)
    title_y = int(H * 0.45)
    body_y = int(H * 0.51)
    max_text_width = int(W * 0.78) 
    paragraph_spacing = int(H * 0.022) 

    # --- FONTS (Using system fallbacks if missing) ---
    f_name_size = int(H * 0.055)
    f_role_size = int(H * 0.035)
    f_loc_size = int(H * 0.024)   # Smaller font size for location
    f_title_size = int(H * 0.045)
    f_body_size = int(H * 0.024)

    def load_smart_font(font_name, size, is_bold=False):
        font_path = os.path.join(app.config['FONT_FOLDER'], font_name)
        try:
            return ImageFont.truetype(font_path, size)
        except IOError:
            # Fallback to Times New Roman for that classic, elegant look
            fallback = "timesbd.ttf" if is_bold else "times.ttf"
            try:
                return ImageFont.truetype(fallback, size)
            except IOError:
                # If Times isn't available, try Arial as a last resort before failing
                second_fallback = "arialbd.ttf" if is_bold else "arial.ttf"
                try:
                    return ImageFont.truetype(second_fallback, size)
                except IOError:
                    return ImageFont.load_default()

    # Load the bold/serif fonts to match the Rajvi target
    font_name = load_smart_font('timesbd.ttf', f_name_size, True)
    font_sub_bold = load_smart_font('timesbd.ttf', f_role_size, True)
    font_loc = load_smart_font('timesbd.ttf', f_loc_size, True)
    font_title = load_smart_font('timesbd.ttf', f_title_size, True)
    font_regular = load_smart_font('times.ttf', f_body_size, False)

    # --- DATA PREP ---
    emp_name = data.get('emp_name')
    designation = data.get('designation')
    business_line = data.get('business_line')
    companies = data.get('companies')
    universities = data.get('universities')
    hobbies = data.get('hobbies')
    
    # Pronoun Logic
    gender = str(data.get('gender', 'Female')).strip().lower()
    p_sub = "he" if gender == 'male' else "she"
    p_sub_cap = "He" if gender == 'male' else "She"
    p_obj_lower = "his" if gender == 'male' else "her"
    p_object = "him" if gender == 'male' else "her"


    # --- PROCESS & PASTE AMBIT LOGO ---
    if os.path.exists(app.config['LOGO_PATH']):
        logo = Image.open(app.config['LOGO_PATH']).convert("RGBA")
        
        # Calculate height automatically maintaining aspect ratio
        w_orig, h_orig = logo.size
        aspect_ratio = h_orig / w_orig
        logo_h = int(logo_w * aspect_ratio)
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
        
        # Position logo: right aligned with top right corner
        logo_x = W - logo_w - logo_right_margin
        base_image.paste(logo, (logo_x, logo_top_margin), logo)
    else:
        print(f"Warning: Ambit logo not found at {app.config['LOGO_PATH']}. Slide will be generated without it.")

    # --- PROCESS & PASTE PROFILE PHOTO ---
    headshot = Image.open(photo_path).convert("RGBA")
    # Perfectly centers and crops the image to a square
    headshot = ImageOps.fit(headshot, (photo_diameter, photo_diameter), centering=(0.5, 0.5))
    
    # Create the circular mask
    mask = Image.new('L', (photo_diameter, photo_diameter), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, photo_diameter, photo_diameter), fill=255)
    headshot.putalpha(mask)
    
    base_image.paste(headshot, (photo_x, photo_y), headshot) 
    
    # --- DRAW TEXT ---
    draw = ImageDraw.Draw(base_image)
    ambit_red = (220, 25, 45) # Corporate red matching template accent

    # 1. Extract data safely first
    emp_name = data.get('emp_name')
    first_name = emp_name.split()[0] if emp_name else ""
    designation = data.get('designation')
    business_line = data.get('business_line')
    department = data.get('department')
    location = data.get('location')
    sector_applicable = data.get('sector_applicable', 'no')
    sector_name = data.get('sector_name', '').strip()

    # --- 2. Top Details (CENTERED IN GREY BOX) ---
    # Name
    draw_centered_text(draw, emp_name, grey_box_center_x, name_y, font_name, (0, 0, 0))
    
    # Designation - Department Line
    role_text = f"{designation} - {department}"
    draw_centered_text(draw, role_text, grey_box_center_x, role_y, font_sub_bold, ambit_red)
    
    # Business Line
    draw_centered_text(draw, business_line, grey_box_center_x, biz_y, font_sub_bold, ambit_red)
    
    # Location (Now using the exact same font size as the two lines above)
    draw_centered_text(draw, location, grey_box_center_x, loc_y, font_sub_bold, ambit_red)
    
    # --- 3. Welcome Title (CENTERED) ---
    draw_centered_text(draw, "Welcome Aboard !", welcome_box_center_x, title_y, font_title, ambit_red)

    

    # --- DYNAMIC BUSINESS/FUNCTION FORMATTING (Para 1) ---
    if business_line == "Group Corporate Office" and department:
        # User request: "within our group corporate office for [function] function"
        business_display = f"Group Corporate Office for the {department} function"
    elif business_line != "Group Corporate Office":
        business_display = f"{business_line} business"
    else:
        business_display = business_line

    # Paragraph 1
    current_y = body_y
    text_color = (50, 50, 50) 
    
    if sector_applicable == 'yes' and sector_name:
        para1 = f"{first_name} joins us as {designation}, covering the {sector_name} sector, within our {business_display}."
    else:
        para1 = f"{first_name} joins us as {designation} within our {business_display}."
        
    current_y = draw_centered_wrapped_text(draw, para1, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing
    # Paragraph 2
    # Grab experience level
    experience_level = data.get('experience_level', 'fresher')

    # --- DYNAMIC PARAGRAPH 2 (Experience) ---
    if experience_level == 'experienced' and companies:
        # Note: using p_sub.lower() prints "he" or "she" with a lowercase letter
        para2 = f"Prior to joining Ambit, {p_sub.lower()} gained valuable experience working with organizations like {companies}."
        current_y = draw_centered_wrapped_text(draw, para2, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing
    # If they are a fresher, we do absolutely nothing! The script just skips to Para 3.
    # Paragraph 3
    # Grab certification and university data
    cert_applicable = str(data.get('cert_applicable', 'no')).strip().lower()
    cert_type = data.get('cert_type', '')
    universities = data.get('universities', '').strip()

    # Dynamic Paragraph 3 Condition
    if cert_applicable == 'yes' and cert_type:
        # If they have a certification (e.g., "Rajvi is a certified Chartered Accountant and she holds an MBA...")
        para3 = f"{first_name} is a certified {cert_type} and {p_sub.lower()} holds {universities}."
    else:
        # If no certification, just print the degree (e.g., "She holds an MBA...")
        para3 = f"{first_name} holds {universities}."

    current_y = draw_centered_wrapped_text(draw, para3, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing
    # Paragraph 4
    para4 = f"Beyond {p_obj_lower} professional accomplishments, {first_name} is passionate about {hobbies}."
    current_y = draw_centered_wrapped_text(draw, para4, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing

    # Paragraph 5
    para5 = f"We are excited to have {first_name} on board and look forward to the energy {p_sub.lower()} will bring to the team."
    current_y = draw_centered_wrapped_text(draw, para5, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing
    
    # Paragraph 6 (New closing line in your image)
    para6 = f"Please join us in extending a warm welcome to {p_object} and wishing {p_object} every success as {p_sub} begins {p_obj_lower} journey with Ambit."
    draw_centered_wrapped_text(draw, para6, welcome_box_center_x, current_y, max_text_width, font_regular, text_color)
    
    base_image.save(output_path, format="PNG")
    return output_path

# --- ROUTES ---
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    form_data = {
        'emp_name': request.form.get('emp_name'),
        'gender': request.form.get('gender'), 
        'designation': request.form.get('designation'),
        'business_line': request.form.get('business_line'),
        'department': request.form.get('department'),           # NEW
        'location': request.form.get('location'),
        'function_name': request.form.get('function_name'),
        'sector_applicable':request.form.get('sector_applicable'),
        'sector_name':request.form.get('sector_name'),
        'cert_applicable': request.form.get('cert_applicable'), 
        'cert_type': request.form.get('cert_type'),
        'experience_level': request.form.get('experience_level'),
        'companies': request.form.get('companies'),
        'universities': request.form.get('universities'),
        'hobbies': request.form.get('hobbies')
    }

    photo = request.files.get('emp_photo')
    if not photo or photo.filename == '':
        return "Error: Please upload an employee photo.", 400

    filename = secure_filename(photo.filename)
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    photo.save(photo_path)
    
    final_filename = f"welcome_{form_data['emp_name'].replace(' ', '_')}.png"
    final_path = os.path.join(app.config['GENERATED_FOLDER'], final_filename)
    
    create_welcome_image_auto(form_data, photo_path, final_path)
    
    return render_template('preview.html', image_url=final_path, emp_name=form_data['emp_name'], business_line=form_data['business_line'])

@app.route('/send_email', methods=['POST'])
def send_email():
    target_email = request.form.get('target_email')
    cc_email = request.form.get('cc_email') # Grab the CC email from the form
    emp_name = request.form.get('emp_name', 'Team Member')
    business_line = request.form.get('business_line', 'Ambit') 
    
    # Reconstruct the exact image path based on the employee's name
    final_filename = f"welcome_{emp_name.replace(' ', '_')}.png"
    image_path = os.path.join(app.config['GENERATED_FOLDER'], final_filename)
    
    # 1. Validate inputs
    if not target_email:
        return "Error: Recipient email is required.", 400
    if not os.path.exists(image_path):
        return f"Error: Generated image not found at {image_path}.", 500

    # 2. Load credentials from .env
    smtp_host = os.getenv('ZEPTO_SMTP_HOST', 'smtp.zeptomail.in')
    smtp_port = int(os.getenv('ZEPTO_SMTP_PORT', 587))
    smtp_user = os.getenv('ZEPTO_SMTP_USER')
    smtp_pass = os.getenv('ZEPTO_SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL')

    if not smtp_user or not smtp_pass:
        return "Error: SMTP credentials are missing from the .env file.", 500

    # 3. Construct the Email 
    msg = MIMEMultipart('related')
    msg['Subject'] = f"Warm Welcome - New Joinee | {emp_name} | {business_line}"
    msg['From'] = f"Ambit HR <{from_email}>"
    msg['To'] = target_email
    
    # Add the CC header if the HR person typed one in
    if cc_email:
        msg['Cc'] = cc_email
        msg['Bcc'] = "AmbitHR@ambit.co"

    # Create the HTML body
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            
            
            <div style="margin-top: 20px;">
                <img src="cid:welcome_image" alt="Welcome {emp_name}" style="max-width: 100%; border: 1px solid #ddd; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);">
            </div>
            
            <p style="margin-top: 30px; font-size: 12px; color: #888;">
                Best regards,<br>
                <b>Ambit HR</b>
            </p>
        </body>
    </html>
    """
    
    # Attach HTML to the email
    msg.attach(MIMEText(html_body, 'html'))

    # 4. Read the generated image and attach it inline
    try:
        with open(image_path, 'rb') as img_file:
            img_data = img_file.read()
            
        image = MIMEImage(img_data, name=final_filename)
        image.add_header('Content-ID', '<welcome_image>')
        image.add_header('Content-Disposition', 'inline', filename=final_filename)
        msg.attach(image)
        
    except Exception as e:
        return f"Failed to attach image: {str(e)}", 500

    # 5. Connect to ZeptoMail and Send!
    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls() 
        server.login(smtp_user, smtp_pass)
        
        # server.send_message automatically extracts the To and Cc headers we set above!
        server.send_message(msg)
        server.quit()
        
        # Dynamic success message
        cc_text = f" and copied to <b>{cc_email}</b>" if cc_email else ""
        
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: #28a745;">Success!</h2>
            <p>The welcome email for <b>{emp_name}</b> has been sent to <b>{target_email}</b>{cc_text}.</p>
            <a href="/" style="padding: 10px 20px; background-color: #d81b60; color: white; text-decoration: none; border-radius: 5px;">Create Another</a>
        </div>
        """
        
    except Exception as e:
        return f"<h3>Failed to send email via ZeptoMail:</h3><p>{str(e)}</p>", 500
if __name__ == '__main__':
    app.run(debug=True, port=5000)