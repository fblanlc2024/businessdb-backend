from reportlab.lib import colors
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepInFrame
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO

from .dashed_box import DashedBox

class StaticPDF:
    def __init__(self):
        pass

    def create_business_pdf(data, formatted_addresses):
        """
            Creates a PDF document containing a business report based on provided data and addresses.

            Args:
                data (dict): Dictionary containing business data.
                formatted_addresses (list): List of formatted addresses.

            Returns:
                bytes: PDF document in bytes format.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()

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

        colWidths = [doc.width/3.0, doc.width/3.0 * 2]

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
        elements += StaticPDF.create_executive_summary(data)
        elements.append(Spacer(1, 12))

        business_logo = data.get('logo_url', None)
        max_width = 6 * inch
        max_height = 2 * inch

        if business_logo:
            try:
                logo = Image(business_logo)

                aspect = logo.imageWidth / logo.imageHeight
                if aspect > 1:
                    logo.drawWidth = min(max_width, logo.imageWidth)
                    logo.drawHeight = logo.drawWidth / aspect
                else:
                    logo.drawHeight = min(max_height, logo.imageHeight)
                    logo.drawWidth = logo.drawHeight * aspect

                elements.append(logo)
                elements.append(Spacer(1, 12))
            except Exception as e:
                print(f"Error loading image: {e}")

        elements.append(table)

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

        has_resources = data.get('has_available_resources', False)
        resources = data.get('resources_available', '').split(', ')

        if has_resources and resources:
            pie_chart_buffer = StaticPDF.create_random_pie_chart(resources)
            pie_chart_image = Image(pie_chart_buffer)

            pie_chart_width = 4 * inch
            aspect_ratio = pie_chart_image.imageWidth / pie_chart_image.imageHeight
            pie_chart_height = pie_chart_width / aspect_ratio

            pie_chart_image.drawWidth = pie_chart_width
            pie_chart_image.drawHeight = pie_chart_height

            elements.append(pie_chart_image)
            elements.append(Spacer(1, 12))
        
        else:
            centered_style = ParagraphStyle('centered_style', alignment=1)
            message = "There are no available resources at this time."
            no_resource_message = Paragraph(message, centered_style)

            box_width = doc.width * 0.5
            box_height = 2 * inch

            dashed_box = DashedBox(no_resource_message, box_width, box_height)
            centered_table = Table([[dashed_box]], colWidths=[doc.width])
            centered_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

            elements.append(Spacer(1, 12))
            elements.append(centered_table)
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

            table_data.extend([
                ['Business ID', data.get('business_id', '')],
                ['Business Name', data.get('business_name', '')],
                ['Organization Type', data.get('organization_type', '')],
                ['Resources Available', data.get('resources_available', '')],
                ['Has Available Resources', 'Yes' if data.get('has_available_resources') else 'No'],
                ['Contact Info', data.get('contact_info', '')]
            ])

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

            if yearly_revenue != 'Not Available':
                revenue_description = "High" if float(yearly_revenue) > 1000000 else "Moderate"
                table_data.append(['Revenue Description', f"The business has a {revenue_description} revenue stream."])

            if employee_count != 'Not Available':
                employee_description = "Large" if int(employee_count) > 100 else "Small to Medium"
                table_data.append(['Employee Description', f"The business is categorized as a {employee_description} sized enterprise."])
        else:
            print("Invalid data format: Expected a dictionary")
            return None

        colWidths = [doc.width/3.0, doc.width/3.0 * 2]

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
        elements += StaticPDF.create_executive_summary(data)
        elements.append(Spacer(1, 12))

        business_logo = data.get('logo_url', None)
        max_width = 6 * inch
        max_height = 2 * inch

        if business_logo:
            try:
                logo = Image(business_logo)

                aspect = logo.imageWidth / logo.imageHeight
                if aspect > 1:
                    logo.drawWidth = min(max_width, logo.imageWidth)
                    logo.drawHeight = logo.drawWidth / aspect
                else:
                    logo.drawHeight = min(max_height, logo.imageHeight)
                    logo.drawWidth = logo.drawHeight * aspect

                elements.append(logo)
                elements.append(Spacer(1, 12))
            except Exception as e:
                print(f"Error loading image: {e}")

        elements.append(table)
        elements.append(Spacer(1, 12))

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

        if yearly_revenue != 'Not Available' and float(yearly_revenue) > 5000000:
            elements.append(Paragraph("This business qualifies for our premium partnership program based on its revenue.", styles['Normal']))
        if employee_count != 'Not Available' and int(employee_count) > 50:
            elements.append(Paragraph("The company's employee count suggests a robust operational capacity.", styles['Normal']))

        revenue_graph_buffer = StaticPDF.create_business_graph('Yearly Revenue', 'Year', 'Revenue (per million $)')
        revenue_graph_image = Image(revenue_graph_buffer)

        graph_image_width = 4 * inch
        aspect_ratio = revenue_graph_image.imageWidth / revenue_graph_image.imageHeight
        graph_image_height = graph_image_width / aspect_ratio

        revenue_graph_image.drawWidth = graph_image_width
        revenue_graph_image.drawHeight = graph_image_height

        elements.append(revenue_graph_image)
        elements.append(Spacer(1, 12))

        has_resources = data.get('has_available_resources', False)
        resources = data.get('resources_available', '').split(', ')

        if has_resources and resources:
            pie_chart_buffer = StaticPDF.create_random_pie_chart(resources)
            pie_chart_image = Image(pie_chart_buffer)

            pie_chart_width = 4 * inch
            aspect_ratio = pie_chart_image.imageWidth / pie_chart_image.imageHeight
            pie_chart_height = pie_chart_width / aspect_ratio

            pie_chart_image.drawWidth = pie_chart_width
            pie_chart_image.drawHeight = pie_chart_height

            elements.append(pie_chart_image)
            elements.append(Spacer(1, 12))
        
        else:
            centered_style = ParagraphStyle('centered_style', alignment=1)
            message = "There are no available resources at this time."
            no_resource_message = Paragraph(message, centered_style)

            box_width = doc.width * 0.5
            box_height = 2 * inch

            dashed_box = DashedBox(no_resource_message, box_width, box_height)

            centered_table = Table([[dashed_box]], colWidths=[doc.width])

            centered_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

            elements.append(Spacer(1, 12))
            elements.append(centered_table)
            elements.append(Spacer(1, 12))

        trend_line_chart_buffer = StaticPDF.create_trend_line_chart()
        trend_line_chart_image = Image(trend_line_chart_buffer)
        trend_line_chart_image.drawWidth = 4 * inch
        trend_line_chart_image.drawHeight = 2.5 * inch
        elements.append(trend_line_chart_image)
        elements.append(Spacer(1, 12))

        doc.build(elements)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf

    @staticmethod
    def create_executive_summary(data):
        """
        Creates an admin-level business report PDF based on provided data and addresses.

        Args:
            data (dict): Dictionary containing business data.
            formatted_addresses (list): List of formatted addresses.

        Returns:
            bytes: PDF document in bytes format.
        """
        styles = getSampleStyleSheet()
        executive_summary = []

        executive_summary.append(Paragraph('<b>Executive Summary</b>', styles['Heading2']))
        executive_summary.append(Spacer(1, 12))

        yearly_revenue = data.get('yearly_revenue', 0)
        employee_count = data.get('employee_count', 0)
        customer_satisfaction = data.get('customer_satisfaction', 0)
        website_traffic = data.get('website_traffic', 0)

        if yearly_revenue and int(yearly_revenue) > 1000000000:
            revenue_analysis = "The company has achieved an impressive revenue of over $1 billion, indicating strong market performance."
        elif yearly_revenue:
            revenue_analysis = "The company has a solid revenue base, showing potential for further growth."
        else:
            revenue_analysis = "Revenue data is not available."
        executive_summary.append(Paragraph(revenue_analysis, styles['Normal']))

        if employee_count > 10000:
            employee_analysis = "With a large employee base, the company demonstrates significant operational capabilities."
        elif employee_count > 0:
            employee_analysis = "The company maintains a lean and efficient workforce."
        else:
            employee_analysis = "Employee count data is not available."
        executive_summary.append(Paragraph(employee_analysis, styles['Normal']))

        if customer_satisfaction >= 4:
            satisfaction_analysis = "High customer satisfaction scores indicate strong customer loyalty and brand value."
        elif customer_satisfaction > 0:
            satisfaction_analysis = "Customer satisfaction is fair, with room for improvement."
        else:
            satisfaction_analysis = "Customer satisfaction data is not available."
        executive_summary.append(Paragraph(satisfaction_analysis, styles['Normal']))

        if website_traffic > 1000000:
            traffic_analysis = "The substantial website traffic highlights the company's strong online presence and engagement."
        elif website_traffic > 0:
            traffic_analysis = "The company has a moderate online audience, with opportunities for digital growth."
        else:
            traffic_analysis = "Website traffic data is not available."
        executive_summary.append(Paragraph(traffic_analysis, styles['Normal']))

        executive_summary.append(Spacer(1, 12))

        return executive_summary

    @staticmethod
    def create_business_graph(title, x_label, y_label, num_years=10, min_value=100, max_value=500, figsize=(6, 4), degree=4):
        data = [random.uniform(min_value, max_value) for _ in range(num_years)]
        years = np.arange(num_years)
        year_labels = [f'20{20+i}' for i in years]
        plt.style.use('seaborn-v0_8-pastel')
        fig, ax = plt.subplots(figsize=figsize)

        print(f"PLOT STYLES AVAILABLE: {plt.style.available}")

        bars = ax.bar(years, data, alpha=0.7, label='Revenue')

        z = np.polyfit(years, data, degree)
        p = np.poly1d(z)
        plt.plot(years, p(years), "r--", label='Trend')

        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, yval, round(yval, 2), va='bottom', ha='center', fontsize='small')

        ax.set_xlabel(x_label, fontsize='medium')
        ax.set_ylabel(y_label, fontsize='medium')
        ax.set_xticks(years)
        ax.set_xticklabels(year_labels, fontsize='small')
        ax.set_title(title, fontsize='large')

        ax.legend(fontsize='small')

        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf

    @staticmethod
    def create_random_pie_chart(resources):
        percentages = np.random.rand(len(resources))
        percentages /= percentages.sum()

        if not np.isclose(percentages.sum(), 1):
            return StaticPDF.create_random_pie_chart(resources)

        fig, ax = plt.subplots()
        ax.pie(percentages, labels=resources, autopct='%1.1f%%')
        buf = BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)

        return buf

    @staticmethod
    def create_trend_line_chart(hours=24, figsize=(6, 4)):
        x_labels = [f"{i}:00" for i in range(hours)]

        visitor_counts = np.random.randint(0, 500, size=hours)

        plt.figure(figsize=figsize)
        plt.plot(x_labels, visitor_counts, marker='o', linestyle='-', color='b')
        plt.title('Hourly Site Visitors')
        plt.xlabel('Hour of the Day')
        plt.ylabel('Number of Visitors')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.grid(True)

        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        plt.close()
        buffer.seek(0)
        
        return buffer