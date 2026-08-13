from calibre.customize import InterfaceActionBase


class CalibreAwardsPlugin(InterfaceActionBase):
    name = 'Calibre Awards'
    description = 'Find literary awards associated with books and stories'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Agris Taurins'
    version = (0, 0, 1)
    minimum_calibre_version = (9, 13, 0)
    actual_plugin = 'calibre_plugins.calibre_awards.ui:CalibreAwardsAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        # Import lazily so command-line Calibre tools do not load Qt.
        from calibre_plugins.calibre_awards.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()

