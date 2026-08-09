from calibre.customize import InterfaceActionBase


class CalibreAwardsPlugin(InterfaceActionBase):
    name = 'Calibre Awards'
    description = 'Find literary awards associated with books and stories'
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Agris Taurins'
    version = (0, 0, 1)
    minimum_calibre_version = (9, 13, 0)
    actual_plugin = 'calibre_plugins.calibre_awards.ui:CalibreAwardsAction'
