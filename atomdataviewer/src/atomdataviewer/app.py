"""
Extract, Display, and Convert Atom Flight Logs
"""

import toga
from toga.style.pack import COLUMN, ROW, LEFT, RIGHT

import mwhlogging
from mwhlogging import mwhLogger 

class AtomDataViewer(toga.App):

	home = (40.1310941,-75.4461272)
	drone = (40.1210654, -75.466978)

	def startup(self):
		self.map_view = toga.MapView(location=self.home)
		self.map_view.pins.add(toga.MapPin(self.home,title="home"))
		self.map_view.pins.add(toga.MapPin(self.drone,title="drone"))

		self.table_view = toga.Table(headings=["A","B","C","D"])

		container = toga.OptionContainer()
		container.content.append("Map", self.map_view)
		container.content.append("Table", self.table_view)

		self.main_window = toga.MainWindow(title=self.formal_name, size=(800,600))
		self.main_window.content = container
		self.main_window.show()

def main():
	return AtomDataViewer()
