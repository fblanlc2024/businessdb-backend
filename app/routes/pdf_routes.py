from flask import Blueprint, make_response, request, jsonify
from reportlab.lib import colors
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepInFrame
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

from app import db
businesses_collection = db.businesses
pdf_routes_bp = Blueprint('pdf_routes_bp', __name__)

@pdf_routes_bp.route('/print_business_info', methods=['POST'])
def print_business_info():
    data = request.get_json()
    is_admin = data.get('isAdmin', 'false').lower() == 'true'
    business_info = data.get('businessData', {})
    formatted_addresses = data.get('formattedAddresses', [])

    if business_info:
        if is_admin:
            pdf = create_admin_business_pdf(business_info, formatted_addresses)
        else:
            pdf = create_business_pdf(business_info, formatted_addresses)
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={business_info.get("business_name", "report")}.pdf'
        return response
    else:
        return jsonify({"error": "Business data not provided"}), 400

def create_business_pdf(data, formatted_addresses):
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
    elements += create_executive_summary(data)
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

    # Create the address table
    address_table_data = [['Address Number', 'Address Data']]
    for i, address in enumerate(formatted_addresses, 1):
        address_label = f"Address {i}"
        address_table_data.append([address_label, address])


    address_table = Table(address_table_data, colWidths=[doc.width/3.0, doc.width/3.0 * 2])
    address_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements.append(address_table)
    elements.append(Spacer(1, 12))

    # Check if there are available resources
    has_resources = data.get('has_available_resources', False)
    resources = data.get('resources_available', '').split(', ')

    if has_resources and resources:
        # Create and add pie chart
        pie_chart_buffer = create_random_pie_chart(resources)
        pie_chart_image = Image(pie_chart_buffer)

        # Resize the pie chart image
        pie_chart_width = 4 * inch
        aspect_ratio = pie_chart_image.imageWidth / pie_chart_image.imageHeight
        pie_chart_height = pie_chart_width / aspect_ratio

        pie_chart_image.drawWidth = pie_chart_width
        pie_chart_image.drawHeight = pie_chart_height

        elements.append(pie_chart_image)
        elements.append(Spacer(1, 12))
    
    else:
        # Display a message in a dashed box
        message = "There are no available resources at this time."
        no_resource_message = Paragraph(message, styles['Normal'])
        dash_box = KeepInFrame(doc.width, 2 * inch, [no_resource_message], vAlign='middle', hAlign='center', style=TableStyle([
        ('BOX', (0,0), (-1,-1), 2, colors.black, 'dashed'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(dash_box)
        elements.append(Spacer(1, 12))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def create_admin_business_pdf(data, formatted_addresses):
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
    elements += create_executive_summary(data)
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

    # Create the address table
    address_table_data = [['Address Number', 'Address Data']]
    for i, address in enumerate(formatted_addresses, 1):
        address_label = f"Address {i}"
        address_table_data.append([address_label, address])

    address_table = Table(address_table_data, colWidths=[doc.width/3.0, doc.width/3.0 * 2])
    address_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements.append(address_table)
    elements.append(Spacer(1, 12))

    # Additional Text
    if yearly_revenue != 'Not Available' and float(yearly_revenue) > 5000000:
        elements.append(Paragraph("This business qualifies for our premium partnership program based on its revenue.", styles['Normal']))
    if employee_count != 'Not Available' and int(employee_count) > 50:
        elements.append(Paragraph("The company's employee count suggests a robust operational capacity.", styles['Normal']))

    # Create the graph image and resize it
    revenue_graph_buffer = create_business_graph('Yearly Revenue', 'Year', 'Revenue (per million $)')
    revenue_graph_image = Image(revenue_graph_buffer)

    # Let's assume you want the image to be 4 inches wide and the height to be scaled proportionally
    graph_image_width = 4 * inch
    aspect_ratio = revenue_graph_image.imageWidth / revenue_graph_image.imageHeight
    graph_image_height = graph_image_width / aspect_ratio

    revenue_graph_image.drawWidth = graph_image_width
    revenue_graph_image.drawHeight = graph_image_height

    # Add the resized graph image to the elements
    elements.append(revenue_graph_image)
    elements.append(Spacer(1, 12))

    # Check if there are available resources
    has_resources = data.get('has_available_resources', False)
    resources = data.get('resources_available', '').split(', ')

    if has_resources and resources:
        # Create and add pie chart
        pie_chart_buffer = create_random_pie_chart(resources)
        pie_chart_image = Image(pie_chart_buffer)

        # Resize the pie chart image
        pie_chart_width = 4 * inch
        aspect_ratio = pie_chart_image.imageWidth / pie_chart_image.imageHeight
        pie_chart_height = pie_chart_width / aspect_ratio

        pie_chart_image.drawWidth = pie_chart_width
        pie_chart_image.drawHeight = pie_chart_height

        elements.append(pie_chart_image)
        elements.append(Spacer(1, 12))
    
    else:
        # Display a message in a dashed box
        message = "There are no available resources at this time."
        no_resource_message = Paragraph(message, styles['Normal'])
        dash_box = KeepInFrame(doc.width, 2 * inch, [no_resource_message], vAlign='middle', hAlign='center', style=TableStyle([
        ('BOX', (0,0), (-1,-1), 2, colors.black, 'dashed'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(dash_box)
        elements.append(Spacer(1, 12))

    # Build the PDF
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def create_executive_summary(data):
    styles = getSampleStyleSheet()
    executive_summary = []

    executive_summary.append(Paragraph('<b>Executive Summary</b>', styles['Heading2']))
    executive_summary.append(Spacer(1, 12))

    yearly_revenue = data.get('yearly_revenue', 0)
    employee_count = data.get('employee_count', 0)
    customer_satisfaction = data.get('customer_satisfaction', 0)
    website_traffic = data.get('website_traffic', 0)

    # Revenue Analysis
    if yearly_revenue and int(yearly_revenue) > 1000000000:
        revenue_analysis = "The company has achieved an impressive revenue of over $1 billion, indicating strong market performance."
    elif yearly_revenue:
        revenue_analysis = "The company has a solid revenue base, showing potential for further growth."
    else:
        revenue_analysis = "Revenue data is not available."
    executive_summary.append(Paragraph(revenue_analysis, styles['Normal']))

    # Employee Analysis
    if employee_count > 10000:
        employee_analysis = "With a large employee base, the company demonstrates significant operational capabilities."
    elif employee_count > 0:
        employee_analysis = "The company maintains a lean and efficient workforce."
    else:
        employee_analysis = "Employee count data is not available."
    executive_summary.append(Paragraph(employee_analysis, styles['Normal']))

    # Customer Satisfaction
    if customer_satisfaction >= 4:
        satisfaction_analysis = "High customer satisfaction scores indicate strong customer loyalty and brand value."
    elif customer_satisfaction > 0:
        satisfaction_analysis = "Customer satisfaction is fair, with room for improvement."
    else:
        satisfaction_analysis = "Customer satisfaction data is not available."
    executive_summary.append(Paragraph(satisfaction_analysis, styles['Normal']))

    # Website Traffic
    if website_traffic > 1000000:
        traffic_analysis = "The substantial website traffic highlights the company's strong online presence and engagement."
    elif website_traffic > 0:
        traffic_analysis = "The company has a moderate online audience, with opportunities for digital growth."
    else:
        traffic_analysis = "Website traffic data is not available."
    executive_summary.append(Paragraph(traffic_analysis, styles['Normal']))

    executive_summary.append(Spacer(1, 12))

    return executive_summary

def create_business_graph(title, x_label, y_label, num_years=10, min_value=100, max_value=500, figsize=(6, 4), degree=4):
    # Generate pseudo data
    data = [random.uniform(min_value, max_value) for _ in range(num_years)]
    years = np.arange(num_years)
    year_labels = [f'20{20+i}' for i in years]
    plt.style.use('seaborn-v0_8-pastel')
    fig, ax = plt.subplots(figsize=figsize)

    print(f"PLOT STYLES AVAILABLE: {plt.style.available}")

    # Create bar chart
    bars = ax.bar(years, data, alpha=0.7, label='Revenue')

    # Create trend line
    z = np.polyfit(years, data, degree)
    p = np.poly1d(z)
    plt.plot(years, p(years), "r--", label='Trend')

    # Add data labels on the bars
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval, round(yval, 2), va='bottom', ha='center', fontsize='small')

    # Set labels and title
    ax.set_xlabel(x_label, fontsize='medium')  # x-axis label with adjusted font size
    ax.set_ylabel(y_label, fontsize='medium')  # y-axis label with adjusted font size
    ax.set_xticks(years)
    ax.set_xticklabels(year_labels, fontsize='small')  # Half the font size
    ax.set_title(title, fontsize='large')  # Title with adjusted font size

    # Add legend with smaller font size
    ax.legend(fontsize='small')

    # Save to a BytesIO buffer
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)  # Close the figure to free memory

    return buf

def create_random_pie_chart(resources):
    # Randomly distribute percentages among resources
    percentages = np.random.rand(len(resources))
    percentages /= percentages.sum()

    # Check if they sum up to 1 (or close enough due to floating point arithmetic)
    if not np.isclose(percentages.sum(), 1):
        return create_random_pie_chart(resources)  # Retry if not summing up to 1

    fig, ax = plt.subplots()
    ax.pie(percentages, labels=resources, autopct='%1.1f%%')
    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)

    return buf