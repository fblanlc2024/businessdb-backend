from reportlab.platypus import Flowable
from reportlab.lib.units import inch
from reportlab.lib import colors

# General class for dashed box in Reportlab
class DashedBox(Flowable):
    def __init__(self, content, width, height, dash_array=(2, 2)):
        Flowable.__init__(self)
        self.content = content
        self.width = width
        self.height = height
        self.dash_array = dash_array

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        self.canv.saveState()
        self.canv.setDash(self.dash_array)
        self.canv.rect(0, 0, self.width, self.height)
        self.canv.restoreState()

        content_width, content_height = self.content.wrap(self.width, self.height)
        content_x = (self.width - content_width) / 2
        content_y = (self.height - content_height) / 2

        self.content.drawOn(self.canv, content_x, content_y)