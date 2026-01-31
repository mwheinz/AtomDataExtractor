"""
Extract, Display, and Convert Atom Flight Logs
"""

import toga
from toga.style.pack import COLUMN, ROW, LEFT, RIGHT

import mwhlogging
from mwhlogging import mwhLogger 

class AtomDataViewer(toga.App):
	def startup(self):
		"""Construct and show the Toga application.

		Usually, you would add your application to a main content box.
		We then create a main window (with a name matching the app), and
		show the main window.
		"""
		main_box = toga.Box()

		c_box = toga.Box()
		f_box = toga.Box()
		c_input = toga.TextInput(readonly=True)
		f_input = toga.TextInput()
		c_label = toga.Label("Celcius", text_align=LEFT)
		f_label = toga.Label("Fahrenheit", text_align=LEFT)
		join_label = toga.Label("is equivalent to", text_align=RIGHT)

		def calculate(widget):
			try:
				c_input.value = (float(f_input.value) - 32.0) * 5.0 / 9.0
			except ValueError:
				mwhLogger.error(f"{f_input.value} is not a number.")
				c_input.value = "???"

		button = toga.Button("Calculate", on_press=calculate)
		button.style.update(margin_top=5)

		f_box.add(f_input)
		f_box.add(f_label)

		c_box.add(join_label)
		c_box.add(c_input)
		c_box.add(c_label)

		main_box.add(f_box)
		main_box.add(c_box)
		main_box.add(button)

		main_box.style.update(direction=COLUMN, margin=10, gap=10)
		f_box.style.update(direction=ROW, gap=10)
		c_box.style.update(direction=ROW, gap=10)

		c_input.style.update(flex=1)
		f_input.style.update(flex=1, margin_left=210)
		c_label.style.update(width=100)
		f_label.style.update(width=100)
		join_label.style.update(width=200)

		self.main_window = toga.MainWindow(title=self.formal_name)
		self.main_window.content = main_box
		self.main_window.show()

def main():
	return AtomDataViewer()
