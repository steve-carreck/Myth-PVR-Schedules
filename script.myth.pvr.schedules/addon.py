# encoding=utf-8
#                Copyright 2015 - 2020 Steven Carreck
#                    GNU GENERAL PUBLIC LICENSE
#                       Version 3, 29 June 2007
#     This program (Myth PVR Schedules) is free software: you can
#     redistribute it and/or modify it under the terms of the GNU
#     General Public License as published by the Free Software
#     Foundation, either version 3 of the License, or (at your option)
#     any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

__author__ = 'Steven Carreck'

import os
import sys
import threading
import socket
import xbmc
import xbmcaddon
import xbmcgui

_addon_ = xbmcaddon.Addon()
_addon_path_ = _addon_.getAddonInfo('path')
_addon_name_ = _addon_.getAddonInfo('name')
_addon_version_ = _addon_.getAddonInfo('version')
_settings_ = xbmcaddon.Addon(id='script.myth.pvr.schedules')  # http://kodi.wiki/view/Xbmcaddon_module
lib_path = os.path.join(_addon_path_, 'lib')
sys.path.append(lib_path)
import pyxbmct.addonwindow as pyxbmct
import lib.myth_services_api as myth_api
import lib.myth_client as myth_client
debug_mode = False
block_shutdown = False

class KodiGUI(pyxbmct.AddonFullWindow):
    def __init__(self, title=_addon_name_ + ' ' + _addon_version_):
        super(KodiGUI, self).__init__(title)
        if debug_mode:
            debug_log('Init myth_api.MythBackendAPI')
        self.StatusLabel_reset_timer = threading.Timer(2, self.clear_status)
        self.pvr_connected = False
        self.mask_disconnected_message = False
        self.viewMode = 'Main'
        self.RecViewMode = 'Standard'
        # Setup UI
        self.setGeometry(1280, 650, 28, 8)
        self.set_info_controls()
        self.set_active_controls()
        self.set_navigation()
        self.current_recording_rule_dict = {}        # Current rule for editing.
        self.__selected_list_index = ''              # Displaying corresponding programs - focus/schedule change.
        self.__control_focus = ''                    # For returning focus to control after update.
        self.__current_ListSchedules_item = -1       # Used to limit focus updates during mouse move on selected item.
        self.__current_ListPrograms_item = -1        # Used to limit focus updates during mouse move on selected item.
        self.__show_update_results = False           # Some recording option changes need the programs list refreshed.
        self.__schedule_delete = False               # Set to cause full UI refresh when client detects update.
        self.__expect_update = False                 # If an unexpected rule change from another client, notify.

    def set_info_controls(self):
        """ Display passive controls."""
        if debug_mode:
            debug_log('set_info_controls')
        # Label 'Recording Schedules;'
        self.NoIntLabel = pyxbmct.Label(_addon_.getLocalizedString(32010),
                                        alignment=pyxbmct.ALIGN_CENTER, font='font14')
        self.placeControl(self.NoIntLabel, 1, 0, 0, 0)

        # Label 'programs;'
        self.NoIntLabel2 = pyxbmct.Label(_addon_.getLocalizedString(32011),
                                         alignment=pyxbmct.ALIGN_CENTER, font='font14')
        self.placeControl(self.NoIntLabel2, 1, 4, 0, 0)

        # Settings Standard
        # Label 'Recording Group;'
        self.NoIntLabel3 = pyxbmct.Label('  ' + _addon_.getLocalizedString(32046),
                                        alignment=pyxbmct.ALIGN_CENTER,)
        self.placeControl(self.NoIntLabel3, 17, 0, 0, 0)
        self.NoIntLabel3.setVisible(False)

        # Settings Advanced
        # Label 'Storage Group;'
        self.NoIntLabel4 = pyxbmct.Label('  ' + _addon_.getLocalizedString(32055),
                                        alignment=pyxbmct.ALIGN_CENTER,)
        self.placeControl(self.NoIntLabel4, 7, 0, 0, 0)
        self.NoIntLabel4.setVisible(False)

    def set_active_controls(self):
        """ Display active controls."""
        if debug_mode:
            debug_log('set_active_controls')

        # List Item selected label
        # self.StatusLabel = pyxbmct.FadeLabel(textColor='0xFFFFFFFF')
        self.StatusLabel = pyxbmct.FadeLabel(font='font14')
        self.placeControl(self.StatusLabel, 23, 1, columnspan=6)
        self.StatusLabel.reset()

        # List - Recording schedules
        self.ListSchedules = pyxbmct.List()
        self.placeControl(self.ListSchedules, 2, 0, 23, 4)
        # Connect the list to a function to display the programs for the selected recording schedule.
        self.connect(self.ListSchedules, self.list_schedules_click)

        # List - programs
        self.ListPrograms = pyxbmct.List()
        self.placeControl(self.ListPrograms, 2, 4, 23, 4)
        self.connect(self.ListPrograms, self.list_programs_click)

        # Connect key and mouse events to a function ('focus_update', to execute commands depending on focus).
        # http://romanvm.github.io/PyXBMCt/docs/
        self.connectEventList(
            [pyxbmct.ACTION_MOVE_DOWN,
             pyxbmct.ACTION_MOVE_UP,
             pyxbmct.ACTION_MOVE_LEFT,
             pyxbmct.ACTION_MOVE_RIGHT,
             pyxbmct.ACTION_MOUSE_MOVE,
             pyxbmct.ACTION_MOUSE_WHEEL_DOWN,
             pyxbmct.ACTION_MOUSE_WHEEL_UP],
            self.focus_update)

        # Connect remote back button / Backspace to return to main screen from recording settings.
        self.connectEventList([pyxbmct.ACTION_NAV_BACK], self.action_back)

        # Button - Debug
        # self.ButtonDebug = pyxbmct.Button('Debug')
        # self.placeControl(self.ButtonDebug, 25, 5, rowspan=3)
        # self.connect(self.ButtonDebug, self.button_debug_click)

        # Button - Close
        self.ButtonClose = pyxbmct.Button(_addon_.getLocalizedString(32012))
        self.placeControl(self.ButtonClose, 25, 7, rowspan=3)
        # Connect control to close the window.
        self.connect(self.ButtonClose, self.close)

        # Button - Refresh
        self.ButtonRefresh = pyxbmct.Button(_addon_.getLocalizedString(32031))
        self.placeControl(self.ButtonRefresh, 25, 0, rowspan=3)
        self.connect(self.ButtonRefresh, self.button_refresh_click)

        # Add the recording rule settings controls, hidden for initial main view.
        # Button - Apply
        self.ButtonApply = pyxbmct.Button(_addon_.getLocalizedString(32013))
        self.placeControl(self.ButtonApply, 25, 0, rowspan=3)
        self.ButtonApply.setVisible(False)
        self.connect(self.ButtonApply, self.button_apply_click)

        # Button - Delete record schedule
        self.ButtonDelete = pyxbmct.Button(_addon_.getLocalizedString(32014))
        self.placeControl(self.ButtonDelete, 25, 1, rowspan=3)
        self.ButtonDelete.setVisible(False)
        self.connect(self.ButtonDelete, self.button_delete_click)

        # Button - Back
        self.ButtonBack = pyxbmct.Button(_addon_.getLocalizedString(32015))
        self.placeControl(self.ButtonBack, 25, 4, rowspan=3)
        self.connect(self.ButtonBack, self.button_back_click)
        self.ButtonBack.setVisible(False)

        # radio button - 'Single Record'
        self.RadioSingle = pyxbmct.RadioButton(_addon_.getLocalizedString(32016))
        self.placeControl(self.RadioSingle, 2, 0, rowspan=2, columnspan=2)
        self.RadioSingle.setVisible(False)
        self.connect(self.RadioSingle, self.radio_button_recording_single_click)

        # radio button - 'Series Record'
        self.RadioSeries = pyxbmct.RadioButton(_addon_.getLocalizedString(32017))
        self.placeControl(self.RadioSeries, 2, 2, rowspan=2, columnspan=2)
        self.RadioSeries.setVisible(False)
        self.connect(self.RadioSeries, self.radio_button_recording_series_click)

        # radio button - Rec rule filter - 'This_series'
        self.RadioThisSeries = pyxbmct.RadioButton(_addon_.getLocalizedString(32018))
        self.placeControl(self.RadioThisSeries, 4, 0, rowspan=2, columnspan=2)
        self.RadioThisSeries.setVisible(False)
        self.connect(self.RadioThisSeries, self.radio_button_this_series_click)

        # radio button - Rec rule filter - 'This_channel'
        self.RadioThisChannel = pyxbmct.RadioButton(_addon_.getLocalizedString(32019))
        self.placeControl(self.RadioThisChannel, 4, 2, rowspan=2, columnspan=2)
        self.RadioThisChannel.setVisible(False)
        self.connect(self.RadioThisChannel, self.radio_button_this_channel_click)

        # Edit Box for MaxEpisodes.
        self.EditboxMaxEpisodes = pyxbmct.Edit('  ' + _addon_.getLocalizedString(32020))
        self.placeControl(self.EditboxMaxEpisodes, 6, 0, 2, 2)
        self.EditboxMaxEpisodes.setLabel('  ' + _addon_.getLocalizedString(32020))  # NB: Have to set label here also!
        self.EditboxMaxEpisodes.setVisible(False)

        # radio button - Rec rule 'MaxNewest' I.e. Record new and expire old
        self.RadioMaxNewest = pyxbmct.RadioButton(_addon_.getLocalizedString(32021))
        self.placeControl(self.RadioMaxNewest, 6, 2, rowspan=2, columnspan=2)
        self.RadioMaxNewest.setVisible(False)
        self.connect(self.RadioMaxNewest, self.radio_button_max_newest_click)

        # radio button - Rec rule 'AutoExpire'
        self.RadioAutoExpire = pyxbmct.RadioButton(_addon_.getLocalizedString(32022))
        self.placeControl(self.RadioAutoExpire, 8, 0, rowspan=2, columnspan=2)
        self.RadioAutoExpire.setVisible(False)
        self.connect(self.RadioAutoExpire, self.radio_button_auto_expire_click)

        # radio button - Rec rule 'Inactive'
        self.RadioInactive = pyxbmct.RadioButton(_addon_.getLocalizedString(32023))
        self.placeControl(self.RadioInactive, 8, 2, rowspan=2, columnspan=2)
        self.RadioInactive.setVisible(False)
        self.connect(self.RadioInactive, self.radio_button_inactive_click)

        # radio button - Rec rule 'Look up Metadata'
        self.RadioLookupMetadata = pyxbmct.RadioButton(_addon_.getLocalizedString(32024))
        self.placeControl(self.RadioLookupMetadata, 10, 0, rowspan=2, columnspan=2)
        self.RadioLookupMetadata.setVisible(False)
        self.connect(self.RadioLookupMetadata, self.radio_lookup_metadata_click)

        # radio button - Rec rule 'Auto-flag commercials'
        self.RadioAutoFlagCommercials = pyxbmct.RadioButton(_addon_.getLocalizedString(32025))
        self.placeControl(self.RadioAutoFlagCommercials, 10, 2, rowspan=2, columnspan=2)
        self.RadioAutoFlagCommercials.setVisible(False)
        self.connect(self.RadioAutoFlagCommercials, self.radio_auto_flag_commercials_click)

        # radio button - Rec rule 'Auto-transcode'
        self.RadioAutoTranscode = pyxbmct.RadioButton(_addon_.getLocalizedString(32045))
        self.placeControl(self.RadioAutoTranscode, 12, 0, rowspan=2, columnspan=2)
        self.RadioAutoTranscode.setVisible(False)
        self.connect(self.RadioAutoTranscode, self.radio_auto_transcode_click)

        # radio button - Rec rule 'High definition'
        self.RadioHighDef = pyxbmct.RadioButton(_addon_.getLocalizedString(32051))
        self.placeControl(self.RadioHighDef, 12, 2, rowspan=2, columnspan=2)
        self.RadioHighDef.setVisible(False)
        self.connect(self.RadioHighDef, self.radio_high_def_click)

        # Edit Box for Start Early.
        self.EditboxStartEarly = pyxbmct.Edit('  ' + _addon_.getLocalizedString(32052))
        self.placeControl(self.EditboxStartEarly, 14, 0, 2, 2)
        self.EditboxStartEarly.setLabel('  ' + _addon_.getLocalizedString(32052))  # NB: Have to set label here also!
        self.EditboxStartEarly.setText('0')
        self.EditboxStartEarly.setVisible(False)

        # Edit Box for End Late.
        self.EditboxEndLate = pyxbmct.Edit('  ' + _addon_.getLocalizedString(32053))
        self.placeControl(self.EditboxEndLate, 14, 2, 2, 2)
        self.EditboxEndLate.setLabel('  ' + _addon_.getLocalizedString(32053))  # NB: Have to set label here also!
        self.EditboxEndLate.setText('0')
        self.EditboxEndLate.setVisible(False)

        # list - Rec rule 'Recording Groups'
        self.ListRecordingGroups = pyxbmct.List()
        self.placeControl(self.ListRecordingGroups, 16, 2, 3, 2)
        self.ListRecordingGroups.setVisible(False)
        self.connect(self.ListRecordingGroups, self.list_recording_groups_click)

        # Radio Button - Settings Advanced
        self.RadioSettingsAdvanced = pyxbmct.RadioButton(_addon_.getLocalizedString(32054))
        self.placeControl(self.RadioSettingsAdvanced, 18, 0, rowspan=2, columnspan=2)
        self.connect(self.RadioSettingsAdvanced, self.radio_settings_advanced_click)
        self.RadioSettingsAdvanced.setVisible(False)

        # Settings Advanced
        # radio button - Rec rule 'User Job 1'
        self.RadioUserJob1 = pyxbmct.RadioButton(_settings_.getSetting(id="UserJob1"))
        self.placeControl(self.RadioUserJob1, 2, 0, rowspan=2, columnspan=2)
        self.RadioUserJob1.setVisible(False)
        self.connect(self.RadioUserJob1, self.radio_user_job_1_click)

        # radio button - Rec rule 'User Job 2'
        self.RadioUserJob2 = pyxbmct.RadioButton(_settings_.getSetting(id="UserJob2"))
        self.placeControl(self.RadioUserJob2, 2, 2, rowspan=2, columnspan=2)
        self.RadioUserJob2.setVisible(False)
        self.connect(self.RadioUserJob2, self.radio_user_job_2_click)

        # radio button - Rec rule 'User Job 3'
        self.RadioUserJob3 = pyxbmct.RadioButton(_settings_.getSetting(id="UserJob3"))
        self.placeControl(self.RadioUserJob3, 4, 0, rowspan=2, columnspan=2)
        self.RadioUserJob3.setVisible(False)
        self.connect(self.RadioUserJob3, self.radio_user_job_3_click)

        # radio button - Rec rule 'User Job 4'
        self.RadioUserJob4 = pyxbmct.RadioButton(_settings_.getSetting(id="UserJob4"))
        self.placeControl(self.RadioUserJob4, 4, 2, rowspan=2, columnspan=2)
        self.RadioUserJob4.setVisible(False)
        self.connect(self.RadioUserJob4, self.radio_user_job_4_click)

        # list - Rec rule 'Storage Groups'
        self.ListStorageGroups = pyxbmct.List()
        self.placeControl(self.ListStorageGroups, 6, 2, 3, 2)
        self.ListStorageGroups.setVisible(False)
        self.connect(self.ListStorageGroups, self.list_storage_groups_click)

    def action_back(self):
        """ Return from recording rule options."""
        if debug_mode:
            debug_log('action_back')

        if self.viewMode == 'RecRule':
            self.button_back_click()

    def set_navigation(self):
        """ Set navigation between controls."""
        if debug_mode:
            debug_log('set_navigation')

        # Main screen.
        self.ListSchedules.controlLeft(self.ButtonClose)
        self.ListSchedules.controlRight(self.ListPrograms)
        self.ListPrograms.controlLeft(self.ListSchedules)
        self.ListPrograms.controlRight(self.ButtonClose)

        self.ListSchedules.controlUp(self.ButtonRefresh)
        self.ListSchedules.controlDown(self.ButtonRefresh)
        self.ListPrograms.controlUp(self.ButtonClose)
        self.ListPrograms.controlDown(self.ButtonClose)

        # Recording View.
        # Left pane L/R
        self.RadioSingle.controlRight(self.RadioSeries)
        self.RadioSeries.controlLeft(self.RadioSingle)
        self.RadioThisSeries.controlRight(self.RadioThisChannel)
        self.RadioThisChannel.controlLeft(self.RadioThisSeries)
        self.EditboxMaxEpisodes.controlRight(self.RadioMaxNewest)
        self.RadioMaxNewest.controlLeft(self.EditboxMaxEpisodes)
        self.RadioAutoExpire.controlRight(self.RadioInactive)
        self.RadioInactive.controlLeft(self.RadioAutoExpire)
        self.RadioLookupMetadata.controlRight(self.RadioAutoFlagCommercials)
        self.RadioAutoFlagCommercials.controlLeft(self.RadioLookupMetadata)
        self.RadioAutoTranscode.controlRight(self.RadioHighDef)
        self.RadioHighDef.controlLeft(self.RadioAutoTranscode)
        self.EditboxStartEarly.controlRight(self.EditboxEndLate)
        self.EditboxEndLate.controlLeft(self.EditboxStartEarly)
        self.RadioSettingsAdvanced.controlRight(self.ListRecordingGroups)
        self.ListRecordingGroups.controlLeft(self.RadioSettingsAdvanced)

        self.RadioSingle.controlUp(self.ButtonApply)
        self.RadioSingle.controlDown(self.RadioThisSeries)
        self.RadioThisSeries.controlUp(self.RadioSingle)
        self.RadioThisSeries.controlDown(self.EditboxMaxEpisodes)
        self.EditboxMaxEpisodes.controlUp(self.RadioThisSeries)
        self.EditboxMaxEpisodes.controlDown(self.RadioAutoExpire)
        self.RadioAutoExpire.controlUp(self.EditboxMaxEpisodes)
        self.RadioAutoExpire.controlDown(self.RadioLookupMetadata)
        self.RadioLookupMetadata.controlUp(self.RadioAutoExpire)
        self.RadioLookupMetadata.controlDown(self.RadioAutoTranscode)
        self.RadioAutoTranscode.controlUp(self.RadioLookupMetadata)
        self.RadioAutoTranscode.controlDown(self.EditboxStartEarly)
        self.EditboxStartEarly.controlUp(self.RadioAutoTranscode)
        self.EditboxStartEarly.controlDown(self.RadioSettingsAdvanced)
        self.RadioSettingsAdvanced.controlDown(self.ButtonApply)

        # Right pane U/D
        self.RadioSeries.controlUp(self.ButtonDelete)
        self.RadioSeries.controlDown(self.RadioThisChannel)
        self.RadioThisChannel.controlUp(self.RadioSeries)
        self.RadioThisChannel.controlDown(self.RadioMaxNewest)
        self.RadioMaxNewest.controlUp(self.RadioThisChannel)
        self.RadioMaxNewest.controlDown(self.RadioInactive)
        self.RadioInactive.controlUp(self.RadioMaxNewest)
        self.RadioInactive.controlDown(self.RadioAutoFlagCommercials)
        self.RadioAutoFlagCommercials.controlUp(self.RadioInactive)
        self.RadioAutoFlagCommercials.controlDown(self.RadioHighDef)
        self.RadioHighDef.controlUp(self.RadioAutoFlagCommercials)
        self.RadioHighDef.controlDown(self.EditboxEndLate)
        self.EditboxEndLate.controlUp(self.RadioHighDef)
        self.EditboxEndLate.controlDown(self.ListRecordingGroups)
        self.ListRecordingGroups.controlUp(self.EditboxEndLate)
        self.ListRecordingGroups.controlDown(self.ButtonDelete)

        # Advanced settings L/R
        self.RadioUserJob1.controlRight(self.RadioUserJob2)
        self.RadioUserJob2.controlLeft(self.RadioUserJob1)
        self.RadioUserJob3.controlRight(self.RadioUserJob4)
        self.RadioUserJob4.controlLeft(self.RadioUserJob3)
        self.ListStorageGroups.controlLeft(self.RadioSettingsAdvanced)

        # Advanced settings U/D
        self.RadioUserJob1.controlDown(self.RadioUserJob3)
        self.RadioUserJob1.controlUp(self.ButtonApply)
        self.RadioUserJob3.controlDown(self.RadioSettingsAdvanced)
        self.RadioUserJob3.controlUp(self.RadioUserJob1)

        self.RadioUserJob2.controlDown(self.RadioUserJob4)
        self.RadioUserJob2.controlUp(self.ButtonDelete)
        self.RadioUserJob4.controlDown(self.ListStorageGroups)
        self.RadioUserJob4.controlUp(self.RadioUserJob2)
        self.ListStorageGroups.controlUp(self.RadioUserJob4)
        self.ListStorageGroups.controlDown(self.ButtonDelete)

        # Buttons L/R
        self.ButtonApply.controlLeft(self.ButtonClose)
        self.ButtonApply.controlRight(self.ButtonDelete)
        self.ButtonDelete.controlLeft(self.ButtonApply)
        self.ButtonDelete.controlRight(self.ButtonBack)
        self.ButtonBack.controlLeft(self.ButtonDelete)
        self.ButtonBack.controlRight(self.ButtonClose)
        # Buttons U/D
        self.ButtonApply.controlUp(self.RadioSettingsAdvanced)
        self.ButtonApply.controlDown(self.RadioSingle)
        self.ButtonDelete.controlUp(self.ListRecordingGroups)
        self.ButtonDelete.controlDown(self.RadioSeries)
        self.ButtonBack.controlUp(self.ListRecordingGroups)
        self.ButtonBack.controlDown(self.RadioSeries)

    def set_navigation_main(self):
        """ Set navigation between controls for main view."""
        if debug_mode:
            debug_log('set_navigation_main')

        # Up/Down
        self.ButtonRefresh.controlUp(self.ListSchedules)
        self.ButtonRefresh.controlDown(self.ListSchedules)
        self.ButtonClose.controlUp(self.ListPrograms)
        self.ButtonClose.controlDown(self.ListPrograms)
        # Left Right
        self.ButtonRefresh.controlRight(self.ButtonClose)
        self.ButtonRefresh.controlLeft(self.ButtonClose)
        self.ButtonClose.controlRight(self.ButtonRefresh)
        self.ButtonClose.controlLeft(self.ButtonRefresh)
        self.setFocus(self.ListSchedules)

    def set_navigation_record_standard(self):
        """ Set navigation between controls for recording options standard view."""
        if debug_mode:
            debug_log('set_navigation_record_standard')

        # Up/Down
        self.RadioSettingsAdvanced.controlUp(self.EditboxStartEarly)
        self.ButtonClose.controlUp(self.RadioUserJob4)
        self.ButtonClose.controlDown(self.RadioSeries)
        self.ButtonDelete.controlUp(self.ListRecordingGroups)
        # Left Right
        self.ButtonClose.controlRight(self.ButtonApply)
        self.ButtonClose.controlLeft(self.ButtonBack)

    def set_navigation_record_advanced(self):
        """ Set navigation between controls for recording options advanced view."""
        if debug_mode:
            debug_log('set_navigation_record_advanced')

        self.RadioSettingsAdvanced.controlUp(self.RadioUserJob3)
        self.ButtonDelete.controlUp(self.ListStorageGroups)
        self.setFocus(self.RadioUserJob1)

    def focus_update(self):
        """ Show program info per recording schedule list item or series info for program list item."""
        try:
            if self.getFocus() == self.ListSchedules:
                self.__current_ListPrograms_item = -1  # Reset to show series info on first program item.
                self.clear_status()
                if self.pvr_connected:
                    # Filter update - Moving the mouse on a currently selected item fires a focus update multiple times.
                    list_schedules_item_idx = self.ListSchedules.getSelectedPosition()
                    if list_schedules_item_idx != self.__current_ListSchedules_item:
                        self.__current_ListSchedules_item = list_schedules_item_idx
                        if debug_mode:
                            debug_log('focus_update: ListSchedules')
                        self.note_selected_schedule()

            elif self.getFocus() == self.ListPrograms:
                if self.pvr_connected:
                    # Filter update - Moving the mouse on a currently selected item fires a focus update multiple times.
                    list_programs_item_idx = self.ListPrograms.getSelectedPosition()
                    if list_programs_item_idx != self.__current_ListPrograms_item:
                        self.__current_ListPrograms_item = list_programs_item_idx
                        if debug_mode:
                            debug_log('focus_update: ListPrograms')
                        # Show the series info. if available.
                        list_index = int(self.ListPrograms.getSelectedPosition())
                        description = ClsRecPrograms.get_program_per_list_index(list_index)['Description']
                        self.StatusLabel.reset()
                        self.StatusLabel.addLabel(description)

        except (RuntimeError, SystemError):
            pass

        try:
            self.__control_focus = self.getFocus()
        except (RuntimeError, SystemError):
            pass

    def note_selected_schedule(self):
        """ Note the selected schedule for listing corresponding programs and after recording options update."""
        if debug_mode:
            debug_log('note_selected_schedule')

        list_label = self.ListSchedules.getListItem(self.ListSchedules.getSelectedPosition()).getLabel()
        if list_label != 'None':
            self.__selected_list_index = self.ListSchedules.getSelectedPosition()
            self.update_programs_list(self.__selected_list_index)

    def set_animation(self, control):
        """ Set fade animation for all add-on window controls."""
        if debug_mode:
            debug_log('set_animation')

        control.setAnimations([('WindowOpen', 'effect=fade start=0 end=100 time=500',),
                               ('WindowClose', 'effect=fade start=100 end=0 time=500',)])

    def show_connection_status(self):
        """ Show status while trying to connect with Myth Backend."""
        if debug_mode:
            debug_log('show_connection_status - Connecting with Myth PVR')

        self.StatusLabel.reset()
        self.StatusLabel.addLabel(_addon_.getLocalizedString(32026))     # 'Connecting with Myth PVR.'

    def initialise_main_view(self):
        """ Populate UI main view with recording schedules."""
        if debug_mode:
            debug_log('initialise_main_view')

        self.ListSchedules.reset()              # Clear any items - Needed after rule deletion.
        self.set_navigation_main()              # Set control tab order.
        ClsRecSchedules.get_schedules()         # Request list of scheduled from Myth and create list of overrides.
        ClsRecPrograms.cache_programs_list()    # Request and cache list of Programs.
        self.setFocus(self.ListSchedules)       # Set initial focus.
        self.note_selected_schedule()           # Note selected schedule list item and populate programs list.

    def update_recording_rule(self):
        """ Edit rule to match UI. Edit per new rule and http post to Myth."""
        if debug_mode:
            debug_log('update_recording_rule')

        if self.pvr_connected:
            #  Update any recording rule changes from UI to the current recording rule dict.
            new_rule_dict = self.update_rule_from_gui(KodiScheduleUI.current_recording_rule_dict)

            # Edit the dict to match the updated recording rule 'self.__NewRecordingRule_'.
            if debug_mode:
                debug_log('update_recording_rule - Edit Dict to match UI change')

            # HTTP POST a dictionary of rule elements to Myth Backend.
            self.show_status(_addon_.getLocalizedString(32028))  # 'Updating Myth recording schedule.'
            error_info = ClsRecSchedules.set_schedule_rule(new_rule_dict)

            if debug_mode:
                debug_log('Update Rule Dict: ' + str(new_rule_dict))
                debug_log('Result: ' + str(error_info.ErrMessage))

    def update_rule_from_gui(self, current_rule_dict):
        """ Edit rule to match GUI."""
        if debug_mode:
            debug_log('update_rule_from_gui')

        # Standard settings.
        if self.RadioSeries.isSelected():
            current_rule_dict['Type'] = 'Record All'  # Record All, Record One, Channel Record

        if self.RadioSingle.isSelected():
            current_rule_dict['Type'] = 'Single Record'

        if self.RadioThisSeries.isSelected():
            current_rule_dict['FilterThisSeries'] = True
        else:
            current_rule_dict['FilterThisSeries'] = False

        if self.RadioThisChannel.isSelected():
            current_rule_dict['FilterThisChannel'] = True
        else:
            current_rule_dict['FilterThisChannel'] = False

        current_rule_dict['MaxEpisodes'] = self.EditboxMaxEpisodes.getText()

        if self.RadioMaxNewest.isSelected():
            current_rule_dict['MaxNewest'] = True
        else:
            current_rule_dict['MaxNewest'] = False

        if self.RadioAutoExpire.isSelected():
            current_rule_dict['AutoExpire'] = True
        else:
            current_rule_dict['AutoExpire'] = False

        if self.RadioInactive.isSelected():
            current_rule_dict['Inactive'] = True
        else:
            current_rule_dict['Inactive'] = False

        if self.RadioLookupMetadata.isSelected():
            current_rule_dict['AutoMetaLookup'] = True
        else:
            current_rule_dict['AutoMetaLookup'] = False

        if self.RadioAutoFlagCommercials.isSelected():
            current_rule_dict['AutoCommflag'] = True
        else:
            current_rule_dict['AutoCommflag'] = False

        if self.RadioAutoTranscode.isSelected():
            current_rule_dict['AutoTranscode'] = True
        else:
            current_rule_dict['AutoTranscode'] = False

        if self.RadioHighDef.isSelected():
            current_rule_dict['FilterHighDefinition'] = True
        else:
            current_rule_dict['FilterHighDefinition'] = False

        current_rule_dict['StartOffset'] = self.EditboxStartEarly.getText()

        current_rule_dict['EndOffset'] = self.EditboxEndLate.getText()

        current_rule_dict['RecGroup'] = \
            self.ListRecordingGroups.getListItem(self.ListRecordingGroups.getSelectedPosition()).getLabel()

        # Advanced settings.
        if self.RadioUserJob1.isSelected():
            current_rule_dict['AutoUserJob1'] = True
        else:
            current_rule_dict['AutoUserJob1'] = False

        if self.RadioUserJob2.isSelected():
            current_rule_dict['AutoUserJob2'] = True
        else:
            current_rule_dict['AutoUserJob2'] = False

        if self.RadioUserJob3.isSelected():
            current_rule_dict['AutoUserJob3'] = True
        else:
            current_rule_dict['AutoUserJob3'] = False

        if self.RadioUserJob4.isSelected():
            current_rule_dict['AutoUserJob4'] = True
        else:
            current_rule_dict['AutoUserJob4'] = False

        current_rule_dict['StorageGroup'] = \
            self.ListStorageGroups.getListItem(self.ListStorageGroups.getSelectedPosition()).getLabel()

        return current_rule_dict

    def show_updated_recording_rule_results(self):
        """ Refreshes the recording schedules list, programs cache & UI lists after a recording rule change.
        Called by class MythClient when a backend 'SCHEDULE_CHANGE' event occurs."""
        if debug_mode:
            debug_log('show_updated_recording_rule_results')

        # Catch unexpected recording updates - Possibly another client and refresh.
        if not self.__expect_update:
            # 'Recording Schedules', 'Updated via another client.'
            self.__expect_update = False
            self.display_message_dialog(_addon_.getLocalizedString(32010), _addon_.getLocalizedString(32047))
            self.main_view()
            self.initialise_main_view()

        # Reinitialise main view if a schedule is deleted.
        if self.__schedule_delete:
            self.__schedule_delete = False
            self.main_view()
            self.initialise_main_view()

        elif self.viewMode == 'RecRule' and self.__show_update_results:
                self.__show_update_results = False
                # Refresh the recording rule view and list of programs.
                self.show_status(_addon_.getLocalizedString(32028))     # Updating Myth recording schedule.
                ClsRecPrograms.cache_programs_list()                    # Update programs cache list.
                self.update_programs_list(self.__selected_list_index)   # Update the UI programs List.

    def update_programs_list(self, list_index):
        """ List programs per selected recording schedule."""
        if debug_mode:
            debug_log('update_programs_list')

        self.ListPrograms.reset()
        ClsRecPrograms.get_programs(list_index)

    def report_myth_backend_query_error(self, code_or_reason, reply_error_html):
        """ Display backend query error information in Status Label."""

        xbmc.executebuiltin(_addon_.getLocalizedString(32032).format(''))
        # xbmc.executebuiltin('Notification(Error Querying Myth PVR:,{0})'.format(HTTPRequestInfo.ErrReason_))
        error_str = code_or_reason + ": " + reply_error_html
        self.show_status(error_str)

        if debug_mode:
            debug_log('report_myth_backend_query_error: ' + error_str)

    def list_programs_click(self):
        """ Disable or enable a program recording."""
        if debug_mode:
            debug_log('list_programs_click')

        if self.viewMode == 'Main':
            # Record current selected list item positions for returning after list refresh.
            schedules_list_item = self.ListSchedules.getSelectedPosition()
            programs_list_item = self.ListPrograms.getSelectedPosition()

            #  Get the referenced program from the cashed list item and edit to create/delete override 'Dont Record'.
            list_index = int(self.ListPrograms.getSelectedPosition())
            self.__expect_update = True
            result = ClsRecPrograms.toggle_override(list_index)
            if not result.Err:
                self.update_programs_list(self.__selected_list_index)

                # Return to the selected list item positions.
                self.ListSchedules.selectItem(schedules_list_item)
                self.ListPrograms.selectItem(programs_list_item)

        if debug_mode:
            debug_log('list_programs_click: html result: ' + result.ErrMessage)

    def radio_button_recording_single_click(self):
        """ Toggle between RadioSeries."""
        if debug_mode:
            debug_log('radio_button_recording_single_click')

        self.__control_focus = self.getFocus()
        self.__expect_update = True
        self.__show_update_results = True

        if self.RadioSingle.isSelected():
            self.RadioSeries.setSelected(False)
            # Update and refresh the list of programs.
            self.update_recording_rule()            # Post update to Backend.
        else:
            self.RadioSingle.setSelected(True)
            self.update_recording_rule()            # Post update to Backend.

    def radio_button_recording_series_click(self):
        """ Toggle between RadioSingle."""
        if debug_mode:
            debug_log('radio_button_recording_series_click')

        self.__control_focus = self.getFocus()
        self.__expect_update = True
        self.__show_update_results = True

        if self.RadioSeries.isSelected():
            self.RadioSingle.setSelected(False)
            # Preset 'this series' and 'this channel' by default.
            # self.RadioThisSeries.setSelected(True)
            # self.RadioThisChannel.setSelected(True)
            # Update and refresh the list of programs.
            self.update_recording_rule()             # Post update to Backend.
        else:
            self.RadioSeries.setSelected(True)
            self.update_recording_rule()             # Post update to Backend.

    def radio_button_this_series_click(self):
        if debug_mode:
            debug_log('radio_button_this_series_click')

        self.__expect_update = True
        self.__show_update_results = True
        self.update_recording_rule()                 # Post update to Backend.

    def radio_button_this_channel_click(self):
        if debug_mode:
            debug_log('radio_button_this_channel_click')

        self.__expect_update = True
        self.__show_update_results = True
        self.update_recording_rule()                 # Post update to Backend.

    def radio_button_max_newest_click(self):
        if debug_mode:
            debug_log('radio_button_max_newest_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_button_auto_expire_click(self):
        if debug_mode:
            debug_log('radio_button_auto_expire_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_button_inactive_click(self):
        if debug_mode:
            debug_log('radio_button_inactive_click')

        self.__expect_update = True
        self.__show_update_results = True
        self.update_recording_rule()                 # Post update to Backend.

    def radio_lookup_metadata_click(self):
        if debug_mode:
            debug_log('radio_lookup_metadata_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_auto_flag_commercials_click(self):
        if debug_mode:
            debug_log('radio_auto_flag_commercials_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_auto_transcode_click(self):
        if debug_mode:
            debug_log('radio_auto_transcode_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_high_def_click(self):
        if debug_mode:
            debug_log('radio_high_def_click')

        self.__expect_update = True
        self.__show_update_results = True
        self.update_recording_rule()                 # Post update to Backend.

    def list_recording_groups_click(self):
        if debug_mode:
            debug_log('list_recording_groups_click')

        # If the selected item is '<New Group>' show the keyboard. (Find '<')
        list_label = self.ListRecordingGroups.getListItem(self.ListRecordingGroups.getSelectedPosition()).getLabel()
        if list_label[0] == '<':
            # Show the on screen keyboard.
            kbrd = xbmc.Keyboard('', _addon_.getLocalizedString(32044), False)
            kbrd.doModal()
            if kbrd.getText() != '':
                if kbrd.isConfirmed():
                    self.ListRecordingGroups.getListItem(self.ListRecordingGroups.getSelectedPosition())\
                        .setLabel(kbrd.getText())
                    self.__show_update_results = False
                    self.update_recording_rule()                 # Post update to Backend.
        else:
            self.__expect_update = True
            self.__show_update_results = False
            self.update_recording_rule()                 # Post update to Backend.

    def list_storage_groups_click(self):
        if debug_mode:
            debug_log('list_storage_groups_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_user_job_1_click(self):
        if debug_mode:
            debug_log('radio_user_job_1_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_user_job_2_click(self):
        if debug_mode:
            debug_log('radio_user_job_2_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_user_job_3_click(self):
        if debug_mode:
            debug_log('radio_user_job_3_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def radio_user_job_4_click(self):
        if debug_mode:
            debug_log('radio_user_job_4_click')

        self.__expect_update = True
        self.__show_update_results = False
        self.update_recording_rule()                 # Post update to Backend.

    def button_apply_click(self):
        """ Apply recording option changes and refresh schedules & programs lists."""
        if debug_mode:
            debug_log('button_apply_click')

        if self.pvr_connected:
            self.__expect_update = True
            self.__show_update_results = True
            self.update_recording_rule()                 # Post update to Backend.

    def button_delete_click(self):
        """ Delete a recording schedule."""
        if debug_mode:
            debug_log('button_delete_click')

        if self.pvr_connected:
            self.__expect_update = True
            self.__schedule_delete = True
            error_info = ClsRecSchedules.remove_schedule(self.__selected_list_index)

            if not error_info.Err:
                self.__selected_list_index = 0

            if debug_mode:
                debug_log('Result: ' + str(error_info.ErrMessage))

    def button_back_click(self):
        """ Change UI back to the main view."""
        if debug_mode:
            debug_log('button_back_click')

        if self.pvr_connected:
            self.main_view()
            self.ListSchedules.selectItem(self.__current_ListSchedules_item)
        else:
            self.main_view()

    def button_refresh_click(self):
        """ Reload all schedules & programs from Myth, and refresh lists."""
        if debug_mode:
            debug_log('button_refresh_click')

        self.initialise_main_view()

    def radio_settings_advanced_click(self):
        """ Toggle between Settings Standard & Advanced."""
        if debug_mode:
            debug_log('radio_settings_advanced_click')

        if self.RadioSettingsAdvanced.isSelected():
            self.RecViewMode = 'Advanced'
            self.settings_standard_advanced_show_hide(True, False)
            self.settings_standard_advanced_show_hide(False, True)
            self.set_navigation_record_advanced()
        else:
            self.RecViewMode = 'Standard'
            self.settings_standard_advanced_show_hide(False, False)
            self.settings_standard_advanced_show_hide(True, True)
            self.set_navigation_record_standard()

    def button_debug_click(self):
        """ Debugging only."""
        if debug_mode:
            debug_log('button_debug_click')

        self.StatusLabel.reset()
        self.StatusLabel.addLabel('Debug: ')

    def main_view(self):
        """ Reset UI view if changed from recording view."""
        if debug_mode:
            debug_log('main_view')

        self.viewMode = 'Main'
        self.set_navigation_main()

        # Reset to main view if changed from recording view.
        self.NoIntLabel.setLabel(_addon_.getLocalizedString(32010))    # "Recording Schedules"
        self.ListSchedules.setVisible(True)
        # Hide Standard Settings.
        self.settings_standard_advanced_show_hide(True, False)
        # Hide Advanced Settings.
        self.settings_standard_advanced_show_hide(False, False)
        # Reset settings mode & navigation.
        self.RecViewMode = 'Standard'
        self.RadioSettingsAdvanced.setSelected(False)

    def list_schedules_click(self):
        """ Set recoding rule edit view - hide schedule list, and show recording rule controls."""
        if debug_mode:
            debug_log('list_schedules_click')

        if self.ListSchedules.getListItem(self.ListSchedules.getSelectedPosition()).getLabel2() != 'None':
            self.set_navigation_record_standard()  # Set navigation between standard option controls.
            if self.pvr_connected:
                self.viewMode = 'RecRule'
                # Get Myth backend recording rule and set UI to recording rule.
                error_info = ClsRecSchedules.get_schedule_rule(self.__selected_list_index)
                if not error_info.Err:
                    self.settings_standard_advanced_show_hide(True, True)
                    self.setFocus(self.RadioSingle)

    def set_recording_options_gui(self, rule_dict):
        """ Set the recoding rule UI settings - hide schedule list, and show recording rule controls."""
        if debug_mode:
            debug_log('set_recording_options_gui')

        # Show recording controls & settings.
        self.RadioSettingsAdvanced.setVisible(True)
        self.NoIntLabel.setLabel(_addon_.getLocalizedString(32034))  # "Schedule settings"
        self.ListSchedules.setVisible(False)  # Hide the schedules list.
        # Set standard control values.
        self.RadioInactive.setSelected(string_to_bool(rule_dict['Inactive']))
        self.RadioAutoExpire.setSelected(string_to_bool(rule_dict['AutoExpire']))
        self.RadioLookupMetadata.setSelected(string_to_bool(rule_dict['AutoMetaLookup']))
        self.RadioAutoFlagCommercials.setSelected(string_to_bool(rule_dict['AutoCommflag']))
        self.RadioAutoTranscode.setSelected(string_to_bool(rule_dict['AutoTranscode']))
        self.RadioHighDef.setSelected(rule_dict['FilterHighDefinition'])
        self.EditboxStartEarly.setText(rule_dict['StartOffset'])
        self.EditboxEndLate.setText(rule_dict['EndOffset'])

        # Add recording groups from advanced settings static list.
        settings_static_rec_groups = _settings_.getSetting(id="static_rec_groups")
        settings_static_rec_group_list = settings_static_rec_groups.split(',')
        myth_rec_groups = ClsRecSchedules.get_recording_groups()
        # Add static groups - no duplication.
        for group in settings_static_rec_group_list:
            if not myth_rec_groups.count(group):
                myth_rec_groups.append(group)
        # Show option to add a new group. - Interpreted by click event to open text input box.
        myth_rec_groups.append('<' + _addon_.getLocalizedString(32044) + '>')
        self.ListRecordingGroups.reset()
        self.ListRecordingGroups.addItems(myth_rec_groups)
        # Set the group list item to recording rule.
        for idx in range(0, self.ListRecordingGroups.size()):
            if self.ListRecordingGroups.getListItem(idx).getLabel() == rule_dict['RecGroup']:
                self.ListRecordingGroups.selectItem(idx)
                break

        # Set advanced control values.
        self.RadioUserJob1.setSelected(string_to_bool(rule_dict['AutoUserJob1']))
        self.RadioUserJob2.setSelected(string_to_bool(rule_dict['AutoUserJob2']))
        self.RadioUserJob3.setSelected(string_to_bool(rule_dict['AutoUserJob3']))
        self.RadioUserJob4.setSelected(string_to_bool(rule_dict['AutoUserJob4']))
        # Populate storage group list.
        self.ListStorageGroups.reset()
        self.ListStorageGroups.addItems(ClsRecSchedules.storage_groups())
        for idx in range(0, self.ListStorageGroups.size()):
            if self.ListStorageGroups.getListItem(idx).getLabel() == rule_dict['StorageGroup']:
                self.ListStorageGroups.selectItem(idx)
                break

        if self.RecViewMode == 'Standard':
            # Show these controls depending on single or series record.
            if rule_dict['Type'] == 'Single Record':
                self.RadioSingle.setSelected(True)
                self.RadioSeries.setSelected(False)
                # Hide series related options.
                self.RadioThisSeries.setVisible(False)
                self.RadioThisChannel.setVisible(False)
                self.EditboxMaxEpisodes.setVisible(False)
                self.RadioMaxNewest.setVisible(False)

            elif rule_dict['Type'] == 'Record One' or \
                    rule_dict['Type'] == 'Record All' or \
                    rule_dict['Type'] == 'Record Daily' or \
                    rule_dict['Type'] == 'Record Weekly':
                self.RadioSingle.setSelected(False)
                self.RadioSeries.setSelected(True)
                self.RadioThisSeries.setVisible(True)
                self.RadioThisSeries.setSelected(rule_dict['FilterThisSeries'])
                self.RadioThisChannel.setVisible(True)
                self.RadioThisChannel.setSelected(rule_dict['FilterThisChannel'])
                self.RadioThisChannel.setLabel('This Channel: (' + rule_dict['CallSign'] + ')')
                self.EditboxMaxEpisodes.setVisible(True)
                self.EditboxMaxEpisodes.setText(rule_dict['MaxEpisodes'])
                self.RadioMaxNewest.setVisible(True)
                self.RadioMaxNewest.setSelected(string_to_bool(rule_dict['MaxNewest']))
            else:
                # Unknown recording type.
                self.RadioSingle.setSelected(False)
                self.RadioSeries.setSelected(False)
                self.show_status(_addon_.getLocalizedString(32035))  # Unknown recording type.
            # Show the settings.
            self.settings_standard_advanced_show_hide(True, True)
        else:
            self.settings_standard_advanced_show_hide(False, True)

    def settings_standard_advanced_show_hide(self, standard, show):
        """ Show/hide Settings standard & advanced."""
        if debug_mode:
            debug_log('settings_standard_advanced_show_hide')

        if standard:
            if show:
                # Show Standard Settings.
                self.RadioSingle.setVisible(True)
                self.RadioSeries.setVisible(True)
                self.ButtonApply.setVisible(True)
                self.ButtonDelete.setVisible(True)
                self.ButtonBack.setVisible(True)
                self.RadioThisSeries.setVisible(True)
                self.RadioThisChannel.setVisible(True)
                self.EditboxMaxEpisodes.setVisible(True)
                self.RadioMaxNewest.setVisible(True)
                self.RadioAutoExpire.setVisible(True)
                self.RadioInactive.setVisible(True)
                self.RadioLookupMetadata.setVisible(True)
                self.RadioAutoFlagCommercials.setVisible(True)
                self.RadioAutoTranscode.setVisible(True)
                self.RadioHighDef.setVisible(True)
                self.EditboxStartEarly.setVisible(True)
                self.EditboxEndLate.setVisible(True)
                self.NoIntLabel3.setVisible(True)
                self.ListRecordingGroups.setVisible(True)
                self.RadioSettingsAdvanced.setVisible(True)
            else:
                # Hide Standard Settings.
                self.RadioSingle.setVisible(False)
                self.RadioSeries.setVisible(False)
                self.ButtonApply.setVisible(False)
                self.ButtonDelete.setVisible(False)
                self.ButtonBack.setVisible(False)
                self.RadioThisSeries.setVisible(False)
                self.RadioThisChannel.setVisible(False)
                self.EditboxMaxEpisodes.setVisible(False)
                self.RadioMaxNewest.setVisible(False)
                self.RadioAutoExpire.setVisible(False)
                self.RadioInactive.setVisible(False)
                self.RadioLookupMetadata.setVisible(False)
                self.RadioAutoFlagCommercials.setVisible(False)
                self.RadioAutoTranscode.setVisible(False)
                self.RadioHighDef.setVisible(False)
                self.EditboxStartEarly.setVisible(False)
                self.EditboxEndLate.setVisible(False)
                self.NoIntLabel3.setVisible(False)
                self.ListRecordingGroups.setVisible(False)
                self.RadioSettingsAdvanced.setVisible(False)
        else:
            if show:
                # Show Advanced Settings.
                self.RadioUserJob1.setVisible(True)
                self.RadioUserJob2.setVisible(True)
                self.RadioUserJob3.setVisible(True)
                self.RadioUserJob4.setVisible(True)
                self.NoIntLabel4.setVisible(True)
                self.ListStorageGroups.setVisible(True)
                self.RadioSettingsAdvanced.setVisible(True)
            else:
                self.RadioUserJob1.setVisible(False)
                self.RadioUserJob2.setVisible(False)
                self.RadioUserJob3.setVisible(False)
                self.RadioUserJob4.setVisible(False)
                self.NoIntLabel4.setVisible(False)
                self.ListStorageGroups.setVisible(False)
                self.RadioSettingsAdvanced.setVisible(False)

        # Navigation buttons.
        if show:
            self.ButtonRefresh.setVisible(False)
            self.ButtonApply.setVisible(True)
            self.ButtonDelete.setVisible(True)
            self.ButtonBack.setVisible(True)
        else:
            self.ButtonRefresh.setVisible(True)
            self.ButtonApply.setVisible(False)
            self.ButtonDelete.setVisible(False)
            self.ButtonBack.setVisible(False)

    def show_status(self, status_message=''):
        """ Show status messages."""
        if debug_mode:
            debug_log('show_status: ' + status_message)

        self.StatusLabel_reset_timer.cancel()
        self.StatusLabel.reset()
        self.StatusLabel.addLabel('Status: ' + status_message)
        self.StatusLabel_reset_timer = threading.Timer(2, self.clear_status)
        self.StatusLabel_reset_timer.start()

    def clear_status(self):
        """ Clear status messages after preset amount of time."""
        self.StatusLabel.reset()
        self.StatusLabel.addLabel('Status: ')

    def display_message_dialog(self, heading, message):
        """ Display a notification dialog window."""
        if debug_mode:
            debug_log('display_message_dialog: heading=' + heading + ' message=' + message)

        # http://romanvm.github.io/xbmcstubs/docs/classxbmcgui_1_1_dialog.html#aa7b6cd9b73b30f9a56af5ed40710f533
        dialog = xbmcgui.Dialog()
        dialog.ok(heading, message)

class MythClient(myth_client.MythClient):

    def notify(self, myth_message):
        if myth_message == 'PROTO_REJECT':
            if debug_mode:
                debug_log('MythClient: PROTO_REJECT: ' + myth_message)
            KodiScheduleUI.mask_disconnected_message = True
            KodiScheduleUI.StatusLabel.reset()
            # 'Myth PVR version incompatible: '
            KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32038) + myth_message)

        if myth_message == 'CLIENT_CONNECTED':
            if debug_mode:
                debug_log('CLIENT_CONNECTED')
            KodiScheduleUI.pvr_connected = True

        if myth_message == 'SCHEDULE_CHANGE':
            if debug_mode:
                debug_log('MythClient: SCHEDULE_CHANGE - View mode: ' + KodiScheduleUI.viewMode)

            KodiScheduleUI.show_updated_recording_rule_results()

        if myth_message == 'MASTER_SHUTDOWN' or myth_message == 'SOCK_CLOSE':
            if debug_mode:
                debug_log('MythClient: ' + myth_message)
            # Disable further changes and allow exit only.
            KodiScheduleUI.pvr_connected = False
            KodiScheduleUI.mask_disconnected_message = True
            KodiScheduleUI.StatusLabel.reset()
            # 'Myth PVR server shutting down or disconnected' (or socket closed)
            KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32039))

    def connection_closed(self):
        """ Called when socket closed."""
        if debug_mode:
                debug_log('MythClient: connection_closed')

        # Disable further changes and allow exit only.
        if not KodiScheduleUI.mask_disconnected_message:
            KodiScheduleUI.StatusLabel.reset()
            # 'Myth PVR server disconnected.'
            KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32041))

            if not KodiScheduleUI.pvr_connected:
                KodiScheduleUI.StatusLabel.reset()
                # 'Could not connect to Myth PVR server.'
                KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32042))

        KodiScheduleUI.mask_disconnected_message = False
        KodiScheduleUI.pvr_connected = False

class RecordingRule(myth_api.RecordingRule):

    def schedules_list(self, program_dict, list_index):
        """ Load the UI schedules list."""
        if len(program_dict) != 0:
            list_label = program_dict['Title']
            KodiScheduleUI.ListSchedules.addItem(list_label)
        else:
            KodiScheduleUI.ListSchedules.addItem(_addon_.getLocalizedString(32033))  # None

    def schedule_rule(self, rule_dict):
        """ Set recording rule options UI from recording rule dict, and save for edit."""
        # Store a copy of the recording rule dict for editing.
        KodiScheduleUI.current_recording_rule_dict = rule_dict
        # Show the recording options in UI.
        KodiScheduleUI.set_recording_options_gui(rule_dict)

    def status(self, status_string):
        """ Status info for UI (Schedules load x/x)."""
        KodiScheduleUI.StatusLabel.reset()
        KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32010) + ': ' + status_string)

    def error(self, class_error_info):
        """ Report Myth query error."""
        KodiScheduleUI.report_myth_backend_query_error(class_error_info.ErrCodeOrReason,
                                                       class_error_info.ErrMessage)

class Programs(myth_api.Programs):

    def programs_list(self, program_dict, list_index):
        """ Programs per record schedules list index."""
        if len(program_dict) != 0:
            # Load the schedules list.
            list_label = program_dict['StartDate_str'] + ' ' + program_dict['StartTime_str']\
                + " - " + program_dict['EndTime_str'] + " " + program_dict['CallSign'] \
                + " " + program_dict['Status_str']
            KodiScheduleUI.ListPrograms.addItem(list_label)
        else:
            KodiScheduleUI.ListPrograms.addItem(_addon_.getLocalizedString(32033))  # None

    def status(self, status_string):
        """ Status info for UI (Programs load x/x)."""
        KodiScheduleUI.StatusLabel.reset()
        KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32011) + ': ' + status_string)

    def error(self, class_error_info):
        """ Report Myth query error."""
        KodiScheduleUI.report_myth_backend_query_error(class_error_info.ErrCodeOrReason,
                                                       class_error_info.ErrMessage)

def debug_collect_info():
    """ Collect and log debug info."""
    debug_log('Debugging started.')
    debug_log('Version=' + _addon_.getAddonInfo('version'))
    debug_log('pyxbmct Version=' + xbmc.getInfoLabel('System.AddonVersion("script.module.pyxbmct")'))
    debug_log('System Language=' + xbmc.getInfoLabel('System.Language'))
    debug_log('myth_host=' + _settings_.getSetting(id="myth_host"))
    debug_log('api_port=' + _settings_.getSetting(id="api_port"))
    debug_log('client_port=' + _settings_.getSetting(id="client_port"))
    debug_log('client_security_pin=' + _settings_.getSetting(id="client_security_pin"))
    debug_log('date_format=' + _settings_.getSetting(id="date_format"))
    debug_log('time_format=' + _settings_.getSetting(id="time_format"))
    debug_log('request_size=' + _settings_.getSetting(id="request_size"))
    debug_log('block_myth_pvr_shutdown=' + _settings_.getSetting(id="block_myth_pvr_shutdown"))
    debug_log('wake_on_lan=' + _settings_.getSetting(id="wake_on_lan"))
    debug_log('wake_on_lan_address=' + _settings_.getSetting(id="wake_on_lan_address"))
    debug_log('connection_timeout_seconds=' + _settings_.getSetting(id="connection_timeout_seconds"))
    debug_log('reset_settings=' + _settings_.getSetting(id="reset_settings"))
    debug_log('debug=' + _settings_.getSetting(id="debug"))

def debug_log(message, log_level=xbmc.LOGNOTICE):
    """ Logs debug info to disk."""
    # Debug - $HOME/.kodi/temp/kodi.log, %APPDATA%\Kodi\kodi.log, special://logpath (this can be used by scripts)
    prefix = 'Myth PVR Schedules: '
    xbmc.log(msg=prefix + message, level=log_level)

def validate_settings():
    """ Check for common settings errors and prompt for correction."""
    if debug_mode:
        debug_log('validate_settings')

    if string_to_bool('reset_settings'):
        reset_settings_to_defaults()

    # Validate settings.
    settings_error = check_settings_for_errors()

    while settings_error:
        _settings_.openSettings()  # Open the settings window.

        # Reset settings was selected.
        settings_error = check_settings_for_errors()

        if string_to_bool('reset_settings'):
            reset_settings_to_defaults()

def string_to_bool(true_or_false):
    return 'true' in true_or_false.lower()

def check_settings_for_errors():
    """ Check for settings errors."""
    if debug_mode:
        debug_log('check_settings_for_errors')

    if _settings_.getSetting(id="myth_host") == '?':
        display_setting_error(30001, "myth_host")
        return True

    if _settings_.getSetting(id="api_port") == '':
        display_setting_error(30002, "api_port")
        return True

    if _settings_.getSetting(id="client_port") == '':
        display_setting_error(30003, "client_port")
        return True

    if _settings_.getSetting(id="client_security_pin") == '':
        display_setting_error(30004, "client_security_pin")
        return True

    if _settings_.getSetting(id="connection_timeout_seconds") == '':
        display_setting_error(30012, "connection_timeout_seconds")
        return True

    request_size = _settings_.getSetting(id="request_size")
    if request_size == '':
        display_setting_error(30014, "request_size")
        return True
    elif int(request_size) > 50 or int(request_size) < 1:
        display_setting_error(30014, "request_size")
        return True

def display_setting_error(setting_localized_string_id, setting):
    """ Display settings errors."""
    KodiScheduleUI.display_message_dialog(_addon_.getLocalizedString(32043),
                                          _addon_.getLocalizedString(setting_localized_string_id)
                                          + ': ' + _settings_.getSetting(id=setting))

def reset_settings_to_defaults():
    """ Reset all settings to defaults."""
    if debug_mode:
        debug_log('reset_settings_to_default')

    _settings_.setSetting(id="myth_host", value='?')
    _settings_.setSetting(id="api_port", value='6544')
    _settings_.setSetting(id="client_port", value='6543')
    _settings_.setSetting(id="client_security_pin", value='0000')
    _settings_.setSetting(id="date_format", value='DD-MM-YYYY')
    _settings_.setSetting(id="time_format", value='12Hr')
    _settings_.setSetting(id="block_myth_pvr_shutdown", value='true')
    _settings_.setSetting(id="static_rec_groups", value='')
    _settings_.setSetting(id="wake_on_lan", value='false')
    _settings_.setSetting(id="wake_on_lan_address", value='?')
    _settings_.setSetting(id="connection_timeout_seconds", value='120')
    _settings_.setSetting(id="request_size", value='10')
    _settings_.setSetting(id="reset_settings", value='false')
    _settings_.setSetting(id="debug", value='false')
    _settings_.setSetting(id="UserJob1", value='User Job 1')
    _settings_.setSetting(id="UserJob2", value='User Job 2')
    _settings_.setSetting(id="UserJob3", value='User Job 3')
    _settings_.setSetting(id="UserJob4", value='User Job 4')

def try_wake_on_lan():
    """ validate the WOL setting and execute WOL."""
    if debug_mode:
        debug_log('try_wake_on_lan - addon.py')

    wol_address = str.lower(_settings_.getSetting(id="wake_on_lan_address"))
    if debug_mode:
        debug_log('try_wake_on_lan - addon.py WOL Address: ' + wol_address)

    wol_result = wake_on_lan(wol_address)
    if debug_mode:
        debug_log('try_wake_on_lan - addon.py WOL result: ' + str(wol_result))

    while wol_result != 0 and _settings_.getSetting(id="wake_on_lan") == 'true':
        # 'Advanced settings error', 'Ethernet address - Incorrect format: '
        display_setting_error(30010, "wake_on_lan_address")
        _settings_.openSettings()  # Open the settings window to correct settings.
        wol_address = str.lower(_settings_.getSetting(id="wake_on_lan_address"))
        wol_result = wake_on_lan(wol_address)

def wake_on_lan(mac_address, broadcast_address=''):
    """ Ethernet address delimiter can be ':' or '-', or none.  Broadcast address separated by '.'
    Return 0 if no errors."""
    if debug_mode:
        debug_log('wake_on_lan - addon.py')

    # If no broadcast_address was provided, use the local subnet.
    if broadcast_address == '':
        host_ip = xbmc.getIPAddress()
        if debug_mode:
            debug_log('wake_on_lan - addon.py broadcast_address, host IP: ' + str(host_ip))

        ip = host_ip.split('.')
        broadcast_address = ip[0] + '.' + ip[1] + '.' + ip[2] + '.255'
    if debug_mode:
        debug_log('wake_on_lan - addon.py broadcast_address: ' + str(broadcast_address))

    # Standardise ethernet_address formatting.
    mac_address = mac_address.lower()
    if debug_mode:
        debug_log('wake_on_lan - addon.py mac_address: ' + str(mac_address))

    if mac_address.find(':') > 0:
        octets = mac_address.split(':')
    elif mac_address.find('-') > 0:
        octets = mac_address.split('-')
    else:
        octets = [mac_address[i:i+2] for i in range(0, len(mac_address), 2)]
    if debug_mode:
        debug_log('wake_on_lan - addon.py octets: ' + str(octets))

    # Check mac_address.
    if len(octets) != 6:
        if debug_mode:
            debug_log('wake_on_lan - addon.py len octets != 6: ' + str(octets))
        return -1
    else:
        # Check each list item is 2 chars long.
        for i in range(0, 6):
            if len(octets[i]) != 2:
                if debug_mode:
                    debug_log('wake_on_lan - addon.py octets != 2 each: ' + str(octets))
                return -1

            # Check if all Hex digits.
            try:
                test = int(octets[i], 16)
            except ValueError:
                if debug_mode:
                    debug_log('wake_on_lan - addon.py octets not all Hex: ' + str(octets))
                return -1

    # Check broadcast_address IP.
    address_mask = broadcast_address.split('.')
    if len(address_mask) != 4:
        if debug_mode:
            debug_log('wake_on_lan - addon.py address_mask len != 4 : ' + str(address_mask))
        return -2

    if address_mask[3] != '255':
        if debug_mode:
            debug_log('wake_on_lan - addon.py address_mask not x.x.x.255 : ' + str(address_mask[3]))
        return -2

    for i in range(0, 4):
        try:
            if int(address_mask[i]) == 0:
                if debug_mode:
                    debug_log('wake_on_lan - addon.py address_mask integer.')
                return -2
        except ValueError:
            if debug_mode:
                debug_log('wake_on_lan - addon.py address_mask exception.')
            return -2

    broadcast = '\xff'*6 + (''.join(chr(int(octets[i], 16)) for i in range(0, 5)) + chr(16)) * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.sendto(broadcast, (broadcast_address, 80))

    if debug_mode:
        debug_log('wake_on_lan - addon.py broadcast OK.')
    return 0

def connect_myth_client():
    """ Try to connect and subscribe to Myth server events."""
    if debug_mode:
        debug_log('connect_myth_client - addon.py')

    KodiScheduleUI.StatusLabel.reset()
    KodiScheduleUI.StatusLabel.addLabel(_addon_.getLocalizedString(32036))    # 'Trying to connect...'
    connection_timeout_seconds = int(_settings_.getSetting(id="connection_timeout_seconds"))
    percent = 100
    decrement = percent / float(connection_timeout_seconds)
    myth_client_thread = threading.Thread(target=KodiMythClient)
    user_cancel = False
    progress_bar = xbmcgui.DialogProgress()
    progress_bar.create(_addon_.getLocalizedString(32037))  # "Waiting connection: "

    while percent > decrement and (not user_cancel):
        if KodiScheduleUI.pvr_connected:
            if debug_mode:
                debug_log('KodiMythClient Connected')
            break
        else:
            message = _addon_.getLocalizedString(32037) + str(int(percent))
            progress_bar.update(int(percent), message, '', '')

            if progress_bar.iscanceled():
                user_cancel = True
                break

            if not myth_client_thread.is_alive():
                myth_client_thread = threading.Thread(target=KodiMythClient)
                myth_client_thread.start()

            xbmc.sleep(1000)
            percent -= decrement
    progress_bar.close()

    if KodiScheduleUI.pvr_connected:
        KodiScheduleUI.clear_status()
        return 0
    else:
        return -1

if __name__ == '__main__':
    # If debug mode.
    if _settings_.getSetting(id="debug") == 'true':
        debug_mode = True
        debug_collect_info()

    # Crate the add-on window class.
    if debug_mode:
        debug_log('Init KodiScheduleUI')
    KodiScheduleUI = KodiGUI(_addon_name_ + ' ' + _addon_version_)

    # Show the add-on window asap for the user.
    if debug_mode:
        debug_log('KodiScheduleUI.show')
    KodiScheduleUI.show()

    # Validate settings.
    if debug_mode:
        debug_log('validate_settings')
    validate_settings()

    # Setup Myth Backend API
    MythAPI = myth_api.MythBackendAPI(_settings_.getSetting(id="myth_host"),
                                      _settings_.getSetting(id="api_port"),
                                      _settings_.getSetting(id="client_security_pin"),
                                      _settings_.getSetting(id="date_format"),
                                      _settings_.getSetting(id="time_format"),
                                      _settings_.getSetting(id="request_size"))

    # If the option to Wake on LAN is selected - validate settings and wake.
    if _settings_.getSetting(id="wake_on_lan") == 'true':
        if debug_mode:
            debug_log('wake_on_lan - addon.py - Setting: True')
        try_wake_on_lan()

    # Get the setting to block Myth server shutdown.
    if _settings_.getSetting(id="block_myth_pvr_shutdown") == 'true':
        block_shutdown = True
    if debug_mode:
        debug_log('KodiMythClient.set_block_shutdown - ' + str(block_shutdown))

    # Try to connect and subscribe to Myth server events.
    if debug_mode:
        debug_log('Init KodiMythClient')
    KodiMythClient = MythClient(_settings_.getSetting(id="myth_host"),
                                _settings_.getSetting(id="client_port"), '77 WindMark', block_shutdown, debug_mode)

    # Wait here until connected.
    if debug_mode:
        debug_log('Init KodiMythClient - Waiting at connect_myth_client')
    fail_connect = connect_myth_client()

    if not fail_connect:
        if debug_mode:
            debug_log('Connected to Myth PVR')

        # Init recording rule and programs classes ready for calling list of schedules.
        ClsRecSchedules = RecordingRule()
        ClsRecPrograms = Programs()

        # Init main view.
        if debug_mode:
            debug_log('__Main__ - KodiScheduleUI.initialise_main_view')
        KodiScheduleUI.initialise_main_view()

        # Loop at GUI.
        if debug_mode:
            debug_log('KodiScheduleUI.doModal')
        KodiScheduleUI.doModal()

        # Disconnect from the Myth PVR backend. Also unblocks PVR shutdown if enabled.
        if KodiScheduleUI.pvr_connected:
            if debug_mode:
                debug_log('KodiMythClient.un_subscribe')
            KodiMythClient.disconnect()

        # Wait here until myth client socket closed.
        if debug_mode:
                debug_log('KodiMythClient - wait disconnect.')
        while KodiScheduleUI.pvr_connected:
            xbmc.sleep(250)
    else:
        if debug_mode:
            debug_log('fail_connect = true', xbmc.LOGSEVERE)

    # Destroy the instance explicitly because underlying xbmcgui classes are not garbage-collected on exit.
    if debug_mode:
        debug_log('del KodiScheduleUI')
    del KodiScheduleUI

    if debug_mode:
        debug_log('del KodiScheduleUI - done.')

