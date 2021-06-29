from recOrder.viewer.plugin_offline import OfflineRecon


# each of these dictionaries contains mappings between pyqt widget names, action type, and connecting function name
# {key: value} = {pyqt_widget_name : [action_type, function_name]}
OFFLINE = \
    {
        'qbutton_browse_config_file':   ['clicked', 'set_config_load_path'],
        # 'qbutton_loadconfig':           ['clicked', 'load_configuration_file'],
        # 'qbutton_load_default_config':  ['clicked', 'load_default_config'],
        # 'qbutton_save_config':          ['clicked', 'save_configuration_file'],
        # 'qbutton_runReconstruction':    ['clicked', 'run_reconstruction'],
        # 'qbutton_stopReconstruction':   ['clicked', 'stop_reconstruction'],
    }


class SignalManager:
    """
    manages signal connections between certain GUI elements and their corresponding functions

    """
    # todo: perhaps list function names and connections in a dictionary, similar to how configfile works
    #   then do assignment using setattr/getattr

    def __init__(self, module_type, module):
        if module_type == "offline":

            # INITIALIZE OFFLINE
            OfflineRecon(module)

            # OFFLINE RECONSTRUCTION TAB SIGNALS
            for widget in OFFLINE.items():
                m = getattr(module, widget[0])
                m_action = getattr(m, widget[1][0])
                m_action.connect(getattr(OfflineRecon, widget[1][1]))

        elif module_type == "acquisition":
            pass

        elif module_type == "calibration":
            pass

        elif module_type == 'combined':
            pass

        else:
            raise NotImplementedError()
