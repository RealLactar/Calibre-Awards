from calibre.gui2 import info_dialog
from calibre.gui2.actions import InterfaceAction
from calibre_plugins.calibre_awards.edit_metadata_hook import install_edit_metadata_hook


class CalibreAwardsAction(InterfaceAction):
    name = 'Calibre Awards'
    action_spec = ('Calibre Awards', None, 'Calibre Awards proof of concept', None)

    def genesis(self):
        self.qaction.triggered.connect(self.show_installed_message)

    def initialization_complete(self):
        install_edit_metadata_hook()

    def show_installed_message(self):
        info_dialog(
            self.gui,
            'Calibre Awards',
            'Calibre Awards plugin is installed and running.',
            show=True,
        )
