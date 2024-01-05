class Linker:
    def __init__(self):
        self.link = None

    def add_link(self, business_id, address_id):
        self.link = {
            "business_id": business_id,
            "address_id": address_id
        }

    def to_dict(self):
        return self.link if self.link else {}