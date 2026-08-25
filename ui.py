from calibre.gui2.actions import InterfaceAction
from calibre_plugins.calibre_awards.edit_metadata_hook import (
    install_edit_metadata_hook,
)
from calibre_plugins.calibre_awards.supported_sources_dialog import (
    SupportedSourcesDialog,
)


class CalibreAwardsAction(InterfaceAction):
    """Toolbar/menu action for Supported Award Sources help.

    Check Awards is injected into the single-book Edit Metadata dialog by
    edit_metadata_hook, not by this action.
    """

    name = 'Calibre Awards'
    action_spec = ('Calibre Awards', None, 'Show supported award sources', None)

    def genesis(self):
        icon = get_icons('images/calibre_awards.png', 'Calibre Awards')
        self.qaction.setIcon(icon)
        menuless = getattr(self, 'menuless_qaction', None)
        if menuless is not None:
            menuless.setIcon(icon)
        self.qaction.triggered.connect(self.show_supported_sources)

    def initialization_complete(self):
        # Install after Calibre's GUI exists; the wrapper is idempotent.
        install_edit_metadata_hook()

    def show_supported_sources(self):
        dialog = SupportedSourcesDialog(self.gui)
        dialog.exec()
