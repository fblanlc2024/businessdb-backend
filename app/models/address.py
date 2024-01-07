class Address:
    def __init__(self):
        self.address = None

    def add_address(self, address_id, address_line_1, city, country, state, zipcode, address_line_2=""):
        self.address = {
            "address_id": address_id,
            "address_line_1": address_line_1,
            "address_line_2": address_line_2,
            "city": city,
            "country": country,
            "state": state,
            "zipcode": zipcode
        }

    def to_dict(self):
        return self.address if self.address else {}