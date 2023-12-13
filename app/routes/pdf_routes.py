from flask import Blueprint, make_response, request, jsonify
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

from app import db
businesses_collection = db.businesses
pdf_routes_bp = Blueprint('pdf_routes_bp', __name__)

@pdf_routes_bp.route('/print_business_info', methods=['GET'])
def print_business_info():
    business_name = request.args.get('name')
    is_admin = request.args.get('isAdmin', 'false').lower() == 'true'
    business_info = businesses_collection.find_one({"business_name": business_name})

    if business_info:
        if is_admin:
            pdf = create_admin_business_pdf(business_info)
        else:
            pdf = create_business_pdf(business_info)
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename={}.pdf'.format(business_name)
        return response
    else:
        return jsonify({"error": "Business not found"}), 404

def create_business_pdf(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    # Initialize table data with headers
    table_data = []

    if isinstance(data, dict):
        address = data.get('address', {})
        formatted_address = ', '.join([str(address[key]) for key in address if address[key]])
    
        table_data.append(['Business ID', data.get('business_id', '')])
        table_data.append(['Business Name', data.get('business_name', '')])
        table_data.append(['Address', formatted_address])
        table_data.append(['Organization Type', data.get('organization_type', '')])
        table_data.append(['Resources Available', data.get('resources_available', '')])
        table_data.append(['Has Available Resources', 'Yes' if data.get('has_available_resources') else 'No'])
        table_data.append(['Contact Info', data.get('contact_info', '')])
    else:
        print("Invalid data format: Expected a dictionary")
        return None

    # Define column widths
    colWidths = [doc.width/3.0, doc.width/3.0 * 2]

    # Create the table with style
    table = Table(table_data, colWidths=colWidths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements = []
    elements.append(Paragraph('Business Report For ' + data.get('business_name', ''), styles['Title']))
    elements.append(Spacer(1, 12))

    # Check if the business has a logo and add it to the report
    business_logo = data.get('logo_url', None)
    max_width = 6 * inch  # Example maximum width
    max_height = 2 * inch  # Example maximum height

    if business_logo:
        try:
            logo = Image(business_logo)

            # Calculate aspect ratio and resize
            aspect = logo.imageWidth / logo.imageHeight
            if aspect > 1:
                # Image is wider than it is tall
                logo.drawWidth = min(max_width, logo.imageWidth)
                logo.drawHeight = logo.drawWidth / aspect
            else:
                # Image is taller than it is wide
                logo.drawHeight = min(max_height, logo.imageHeight)
                logo.drawWidth = logo.drawHeight * aspect

            elements.append(logo)
            elements.append(Spacer(1, 12))
        except Exception as e:
            print(f"Error loading image: {e}")

    elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def create_admin_business_pdf(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    table_data = []

    if isinstance(data, dict):
        address = data.get('address', {})
        formatted_address = ', '.join([str(address[key]) for key in address if address[key]])
        
        # Basic Info
        table_data.extend([
            ['Business ID', data.get('business_id', '')],
            ['Business Name', data.get('business_name', '')],
            ['Address', formatted_address],
            ['Organization Type', data.get('organization_type', '')],
            ['Resources Available', data.get('resources_available', '')],
            ['Has Available Resources', 'Yes' if data.get('has_available_resources') else 'No'],
            ['Contact Info', data.get('contact_info', '')]
        ])

        # Admin-specific Info
        yearly_revenue = data.get('yearly_revenue', 'Not Available')
        employee_count = data.get('employee_count', 'Not Available')
        customer_satisfaction = data.get('customer_satisfaction', 'Not Available')
        website_traffic = data.get('website_traffic', 'Not Available')

        table_data.extend([
            ['Yearly Revenue', yearly_revenue],
            ['Employee Count', employee_count],
            ['Customer Satisfaction', customer_satisfaction],
            ['Website Traffic', website_traffic]
        ])

        # Conditional Descriptions
        if yearly_revenue != 'Not Available':
            revenue_description = "High" if float(yearly_revenue) > 1000000 else "Moderate"
            table_data.append(['Revenue Description', f"The business has a {revenue_description} revenue stream."])

        if employee_count != 'Not Available':
            employee_description = "Large" if int(employee_count) > 100 else "Small to Medium"
            table_data.append(['Employee Description', f"The business is categorized as a {employee_description} sized enterprise."])
    else:
        print("Invalid data format: Expected a dictionary")
        return None

    # Define column widths
    colWidths = [doc.width/3.0, doc.width/3.0 * 2]

    # Create the table with style
    table = Table(table_data, colWidths=colWidths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    # Add Table and Additional Text to PDF
    elements = []
    elements.append(Paragraph('Business Report For ' + data.get('business_name', ''), styles['Title']))
    elements.append(Spacer(1, 12))

    business_logo = data.get('logo_url', None)
    max_width = 6 * inch  # Example maximum width
    max_height = 2 * inch  # Example maximum height

    if business_logo:
        try:
            logo = Image(business_logo)

            # Calculate aspect ratio and resize
            aspect = logo.imageWidth / logo.imageHeight
            if aspect > 1:
                # Image is wider than it is tall
                logo.drawWidth = min(max_width, logo.imageWidth)
                logo.drawHeight = logo.drawWidth / aspect
            else:
                # Image is taller than it is wide
                logo.drawHeight = min(max_height, logo.imageHeight)
                logo.drawWidth = logo.drawHeight * aspect

            elements.append(logo)
            elements.append(Spacer(1, 12))
        except Exception as e:
            print(f"Error loading image: {e}")

    elements.append(table)
    elements.append(Spacer(1, 12))

    # Additional Text
    if yearly_revenue != 'Not Available' and float(yearly_revenue) > 5000000:
        elements.append(Paragraph("This business qualifies for our premium partnership program based on its revenue.", styles['Normal']))
    if employee_count != 'Not Available' and int(employee_count) > 50:
        elements.append(Paragraph("The company's employee count suggests a robust operational capacity.", styles['Normal']))

    # Build the PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf