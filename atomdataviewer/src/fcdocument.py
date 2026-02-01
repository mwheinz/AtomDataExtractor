import toga

class FCDocument(toga.document):
	description = "Potensic Atom FC file."
	extensions = [ "fc", "fc2" ]

	def create(self):
