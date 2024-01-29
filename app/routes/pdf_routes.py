from flask import Blueprint, make_response, request, jsonify, current_app
from ..classes.pdf.static_pdf import StaticPDF

from app import db
businesses_collection = db.businesses
pdf_routes_bp = Blueprint('pdf_routes_bp', __name__)

@pdf_routes_bp.route('/print_business_info', methods=['POST'])
def print_business_info():
    data = request.get_json()
    is_admin = data.get('isAdmin', 'false').lower() == 'true'
    business_info = data.get('businessData', {})
    formatted_addresses = data.get('formattedAddresses', [])
    current_app.logger.info(f"business_info received: {business_info}")

    if business_info:
        if is_admin:
            pdf = StaticPDF.create_admin_business_pdf(business_info, formatted_addresses)
        else:
            pdf = StaticPDF.create_business_pdf(business_info, formatted_addresses)
        
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={business_info.get("business_name", "report")}.pdf'
        return response
    else:
        return jsonify({"error": "Business data not provided"}), 400