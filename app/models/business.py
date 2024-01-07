class Business:
    def __init__(self, business_name, organization_type, resources_available, 
                 has_available_resources, contact_info, yearly_revenue, 
                 employee_count, customer_satisfaction, website_traffic):
        self.business_id = None
        self.business_name = business_name
        self.organization_type = organization_type
        self.resources_available = resources_available
        self.has_available_resources = has_available_resources
        self.contact_info = contact_info
        self.yearly_revenue = yearly_revenue
        self.employee_count = employee_count
        self.customer_satisfaction = customer_satisfaction
        self.website_traffic = website_traffic

    def to_dict(self):
        return {
            "business_id": self.business_id,
            "business_name": self.business_name,
            "organization_type": self.organization_type,
            "resources_available": self.resources_available,
            "has_available_resources": self.has_available_resources,
            "contact_info": self.contact_info,
            "yearly_revenue": self.yearly_revenue,
            "employee_count": self.employee_count,
            "customer_satisfaction": self.customer_satisfaction,
            "website_traffic": self.website_traffic,
        }
