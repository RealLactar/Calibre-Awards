from calibre.gui2 import info_dialog
from calibre.gui2.actions import InterfaceAction


class CalibreAwardsAction(InterfaceAction):
    name = 'Calibre Awards'
    action_spec = ('Calibre Awards', None, 'Calibre Awards proof of concept', None)

    def genesis(self):
        self.qaction.triggered.connect(self.show_installed_message)

    def show_installed_message(self):
        info_dialog(
            self.gui,
            'Calibre Awards',
            'Calibre Awards plugin is installed and running.',
            show=True,
        )
