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
app.config['TEMPLATE_FOLDER'] = 'static/template/'
app.config['TEMPLATE_PATH'] = os.path.join(app.config['TEMPLATE_FOLDER'], 'template.png') 
app.config['LOGO_PATH'] = os.path.join(app.config['TEMPLATE_FOLDER'], 'ambit_logo.png') 

app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['GENERATED_FOLDER'] = 'static/generated'
app.config['FONT_FOLDER'] = 'static/fonts'

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

def draw_centered_wrapped_text(draw, text, center_x, y, max_width, font, fill_color, line_spacing=1.3):
    """Wraps text and centers EACH line individually within the max_width boundary."""
    if not text.strip():
        return y
    lines = []
    words = text.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + word + " "
        try:
            width = font.getbbox(test_line)[2]
        except AttributeError:
            width = font.getsize(test_line)[0]
            
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        lines.append(current_line.strip())
        
    try:
        line_height = int(font.getbbox('Ay')[3] * line_spacing)
    except AttributeError:
        line_height = int(font.getsize('Ay')[1] * line_spacing)
        
    current_y = y
    for line in lines:
        draw_centered_text(draw, line, center_x, current_y, font, fill_color)
        current_y += line_height
        
    return current_y

def get_wrapped_text_height(text, max_width, font, line_spacing=1.3):
    """Calculates the total height a wrapped text block will occupy without drawing it."""
    if not text.strip():
        return 0
    lines = []
    words = text.split()
    current_line = ""
    
    for word in words:
        test_line = current_line + word + " "
        try:
            width = font.getbbox(test_line)[2]
        except AttributeError:
            width = font.getsize(test_line)[0]
            
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        lines.append(current_line.strip())
        
    try:
        line_height = int(font.getbbox('Ay')[3] * line_spacing)
    except AttributeError:
        line_height = int(font.getsize('Ay')[1] * line_spacing)
        
    return len(lines) * line_height


# --- AUTO-SCALING IMAGE GENERATOR ---
def create_welcome_image_auto(data, photo_path, output_path):
    base_image = Image.open(app.config['TEMPLATE_PATH']).convert("RGBA")
    W, H = base_image.size 

    # --- LAYOUT CENTERS ---
    photo_diameter = int(W * 0.175)  
    photo_x = int(W * 0.082)         
    photo_y = int(H * 0.115)         

    logo_w = int(W * 0.22)            
    logo_right_margin = int(W * -0.01) 
    logo_top_margin = int(H * -0.03)   

    grey_box_center_x = int(W * 0.66)     

    welcome_box_center_x = int(W * 0.50)
    title_y = int(H * 0.45)
    body_y = int(H * 0.51)
    max_text_width = int(W * 0.78) 
    paragraph_spacing = int(H * 0.022) 

    # --- FONTS ---
    f_name_size = int(H * 0.055)
    f_role_size = int(H * 0.033)  
    f_loc_size = int(H * 0.028)   
    f_title_size = int(H * 0.045)
    f_body_size = int(H * 0.024)

    def load_smart_font(font_name, size, is_bold=False):
        font_path = os.path.join(app.config['FONT_FOLDER'], font_name)
        try:
            return ImageFont.truetype(font_path, size)
        except IOError:
            fallback = "timesbd.ttf" if is_bold else "times.ttf"
            try:
                return ImageFont.truetype(fallback, size)
            except IOError:
                second_fallback = "arialbd.ttf" if is_bold else "arial.ttf"
                try:
                    return ImageFont.truetype(second_fallback, size)
                except IOError:
                    return ImageFont.load_default()

    font_name = load_smart_font('timesbd.ttf', f_name_size, True)
    font_sub_bold = load_smart_font('timesbd.ttf', f_role_size, True)
    font_loc = load_smart_font('timesbd.ttf', f_loc_size, True)
    font_title = load_smart_font('timesbd.ttf', f_title_size, True)
    font_regular = load_smart_font('times.ttf', f_body_size, False)

    # --- DATA PREP ---
    emp_name = data.get('emp_name', '').strip()
    first_name = emp_name.split()[0] if emp_name else ""
    designation = data.get('designation', '').strip()
    business_line = data.get('business_line', '').strip()
    department = data.get('department', '').strip()
    location = data.get('location', '').strip()
    sector_applicable = data.get('sector_applicable', 'no')
    sector_name = data.get('sector_name', '').strip()
    companies = data.get('companies', '').strip()
    universities = data.get('universities', '').strip()
    hobbies = data.get('hobbies', '').strip()
    
    gender = str(data.get('gender', 'Female')).strip().lower()
    p_sub = "he" if gender == 'male' else "she"
    p_sub_cap = "He" if gender == 'male' else "She"
    p_obj_lower = "his" if gender == 'male' else "her"
    p_object = "him" if gender == 'male' else "her"

    # --- PROCESS & PASTE AMBIT LOGO ---
    if os.path.exists(app.config['LOGO_PATH']):
        logo = Image.open(app.config['LOGO_PATH']).convert("RGBA")
        w_orig, h_orig = logo.size
        aspect_ratio = h_orig / w_orig
        logo_h = int(logo_w * aspect_ratio)
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
        logo_x = W - logo_w - logo_right_margin
        base_image.paste(logo, (logo_x, logo_top_margin), logo)

    # --- PROCESS & PASTE PROFILE PHOTO ---
    if os.path.exists(photo_path):
        headshot = Image.open(photo_path).convert("RGBA")
        headshot = ImageOps.fit(headshot, (photo_diameter, photo_diameter), centering=(0.5, 0.5))
        mask = Image.new('L', (photo_diameter, photo_diameter), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, photo_diameter, photo_diameter), fill=255)
        headshot.putalpha(mask)
        base_image.paste(headshot, (photo_x, photo_y), headshot) 

    # --- DRAW TEXT ---
    draw = ImageDraw.Draw(base_image)
    ambit_red = (220, 25, 45) 

    # --- 2. Top Details (DYNAMIC VERTICAL CENTERING FOR GREY BOX) ---
    max_grey_width = int(W * 0.44) 
    block_spacing = int(H * 0.012)
    
    # Define the EXACT visual center of the grey box. 
    # If the text looks slightly too high, change 0.255 to 0.260. If too low, change to 0.250.
    grey_box_center_y = int(H * 0.255) 

    # Prepare specific text fields
    role_text = f"{designation} - {department}" if department else f"{designation}"

    # Calculate individual segment heights
    h_name = get_wrapped_text_height(emp_name, max_grey_width, font_name, line_spacing=0.5)
    h_role = get_wrapped_text_height(role_text, max_grey_width, font_sub_bold, line_spacing=1.15)
    h_biz  = get_wrapped_text_height(business_line, max_grey_width, font_sub_bold, line_spacing=1.15)
    h_loc  = get_wrapped_text_height(location, max_grey_width, font_loc, line_spacing=1.15)

    # Sum up valid active blocks + spacing gaps between them
    active_heights = [h for h in [h_name, h_role, h_biz, h_loc] if h > 0]
    total_text_height = sum(active_heights) + (len(active_heights) - 1) * block_spacing if active_heights else 0

    # Perfect top starting coordinate calculation radiating from the center
    current_top_y = grey_box_center_y - (total_text_height // 2)

    # Render each row safely down the page
    if h_name > 0:
        current_top_y = draw_centered_wrapped_text(
            draw, emp_name, grey_box_center_x, current_top_y, max_grey_width, 
            font_name, (0, 0, 0), line_spacing=1.1
        ) + block_spacing
        
    if h_role > 0:
        current_top_y = draw_centered_wrapped_text(
            draw, role_text, grey_box_center_x, current_top_y, max_grey_width, 
            font_sub_bold, ambit_red, line_spacing=1.15
        ) + block_spacing
        
    if h_biz > 0:
        current_top_y = draw_centered_wrapped_text(
            draw, business_line, grey_box_center_x, current_top_y, max_grey_width, 
            font_sub_bold, ambit_red, line_spacing=1.15
        ) + block_spacing
        
    if h_loc > 0:
        draw_centered_wrapped_text(
            draw, location, grey_box_center_x, current_top_y, max_grey_width, 
            font_loc, ambit_red, line_spacing=1.15
        )
    
    # --- 3. Welcome Title ---
    # draw_centered_text(draw, "Welcome Aboard !", welcome_box_center_x, title_y, font_title, ambit_red)

    # --- 3. DYNAMIC PARAGRAPH GENERATION ---
    # We will put all active paragraphs into a list first, so we can measure their total height!
    paragraphs = []

    # Build Para 1
    if business_line == "Group Corporate Office" and department:
        business_display = f"Group Corporate Office for the {department} function"
    elif business_line != "Group Corporate Office":
        business_display = f"{business_line} business"
    else:
        business_display = business_line

    if sector_applicable == 'yes' and sector_name:
        para1 = f"{first_name} joins us as {designation}, covering the {sector_name} sector, within our {business_display}."
    else:
        para1 = f"{first_name} joins us as {designation} within our {business_display}."
    paragraphs.append(para1)

    # Build Para 2 (Experience - Conditional)
    experience_level = data.get('experience_level', 'fresher')
    if experience_level == 'experienced' and companies:
        para2 = f"Prior to joining Ambit, {p_sub.lower()} gained valuable experience working with organizations like {companies}."
        paragraphs.append(para2)

    # Build Para 3 (Certifications & Education)
    cert_applicable = str(data.get('cert_applicable', 'no')).strip().lower()
    cert_type = data.get('cert_type', '')
    if cert_applicable == 'yes' and cert_type:
        para3 = f"{first_name} is a certified {cert_type} and {p_sub.lower()} holds {universities}."
    else:
        para3 = f"{first_name} holds {universities}."
    paragraphs.append(para3)

    # Build Para 4 (Hobbies)
    para4 = f"Beyond {p_obj_lower} professional accomplishments, {first_name} is passionate about {hobbies}."
    paragraphs.append(para4)

    # Build Para 5 (Energy)
    para5 = f"We are excited to have {first_name} on board and look forward to the energy {p_sub.lower()} will bring to the team."
    paragraphs.append(para5)

    # Build Para 6 (Closing)
    para6 = f"Please Join us in welcoming {first_name} and wishing {p_object} every success as {p_sub} begins {p_obj_lower} journey with Ambit."
    paragraphs.append(para6)

    # --- 4. DYNAMIC VERTICAL CENTERING FOR WELCOME BOX ---
    text_color = (50, 50, 50) 
    title_text = "Welcome Aboard !"
    title_spacing = int(H * 0.005) # The gap between the Welcome title and the first paragraph
    
    # EXACT visual center of the bottom welcome box. 
    # If the whole block needs to move up slightly, change 0.69 to 0.68. If it needs to move down, change to 0.70.
    welcome_box_center_y = int(H * 0.69) 

    # Measure the height of the title and all active paragraphs
    h_title = get_wrapped_text_height(title_text, max_text_width, font_title, line_spacing=1.0)
    p_heights = [get_wrapped_text_height(p, max_text_width, font_regular, line_spacing=1.3) for p in paragraphs]

    # Calculate total height: Title + Space below title + All Paragraph heights + Spacing between paragraphs
    total_welcome_height = h_title + title_spacing + sum(p_heights) + (len(p_heights) - 1) * paragraph_spacing

    # Perfect top starting coordinate calculation
    current_y = welcome_box_center_y - (total_welcome_height // 2)

    # Render the Title
    draw_centered_text(draw, title_text, welcome_box_center_x, current_y, font_title, ambit_red)
    current_y += h_title + title_spacing

    # Render each Paragraph safely down the page
    for p in paragraphs:
        current_y = draw_centered_wrapped_text(draw, p, welcome_box_center_x, current_y, max_text_width, font_regular, text_color) + paragraph_spacing

    base_image.save(output_path, format="PNG")
    return output_path
# --- ROUTES ---
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    form_data = {
        'emp_name': request.form.get('emp_name', ''),
        'gender': request.form.get('gender', 'Female'), 
        'designation': request.form.get('designation', ''),
        'business_line': request.form.get('business_line', ''),
        'department': request.form.get('department', ''),          
        'location': request.form.get('location', ''),
        'function_name': request.form.get('function_name', ''),
        'sector_applicable': request.form.get('sector_applicable', 'no'),
        'sector_name': request.form.get('sector_name', ''),
        'cert_applicable': request.form.get('cert_applicable', 'no'), 
        'cert_type': request.form.get('cert_type', ''),
        'experience_level': request.form.get('experience_level', 'fresher'),
        'companies': request.form.get('companies', ''),
        'universities': request.form.get('universities', ''),
        'hobbies': request.form.get('hobbies', '')
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
    cc_email = request.form.get('cc_email') 
    emp_name = request.form.get('emp_name', 'Team Member')
    business_line = request.form.get('business_line', 'Ambit') 
    
    final_filename = f"welcome_{emp_name.replace(' ', '_')}.png"
    image_path = os.path.join(app.config['GENERATED_FOLDER'], final_filename)
    
    if not target_email:
        return "Error: Recipient email is required.", 400
    if not os.path.exists(image_path):
        return f"Error: Generated image not found at {image_path}.", 500

    smtp_host = os.getenv('ZEPTO_SMTP_HOST', 'smtp.zeptomail.in')
    smtp_port = int(os.getenv('ZEPTO_SMTP_PORT', 587))
    smtp_user = os.getenv('ZEPTO_SMTP_USER')
    smtp_pass = os.getenv('ZEPTO_SMTP_PASS')
    from_email = os.getenv('FROM_EMAIL')

    if not smtp_user or not smtp_pass:
        return "Error: SMTP credentials are missing from the .env file.", 500

    msg = MIMEMultipart('related')
    msg['Subject'] = f"Warm Welcome - New Joinee | {emp_name} | {business_line}"
    msg['From'] = f"Ambit HR <{from_email}>"
    msg['To'] = target_email
    
    if cc_email:
        msg['Cc'] = cc_email
        msg['Bcc'] = "AmbitHR@ambit.co"

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
    
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with open(image_path, 'rb') as img_file:
            img_data = img_file.read()
            
        image = MIMEImage(img_data, name=final_filename)
        image.add_header('Content-ID', '<welcome_image>')
        image.add_header('Content-Disposition', 'inline', filename=final_filename)
        msg.attach(image)
        
    except Exception as e:
        return f"Failed to attach image: {str(e)}", 500

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls() 
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        
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