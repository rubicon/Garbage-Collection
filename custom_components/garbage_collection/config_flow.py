"""Adds config flow for GarbageCollection."""
import logging
import uuid
from datetime import datetime
from typing import Dict

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ENTITIES, CONF_NAME, WEEKDAYS
from homeassistant.core import callback

from . import config_definition
from .const import (
    ANNUAL_FREQUENCY,
    ANNUAL_GROUP_FREQUENCY,
    CONF_COLLECTION_DAYS,
    CONF_EXCLUDE_DATES,
    CONF_EXPIRE_AFTER,
    CONF_FIRST_DATE,
    CONF_FORCE_WEEK_NUMBERS,
    CONF_FREQUENCY,
    CONF_HOLIDAY_POP_NAMED,
    CONF_ICON_NORMAL,
    CONF_ICON_TODAY,
    CONF_ICON_TOMORROW,
    CONF_INCLUDE_DATES,
    CONF_WEEK_ORDER_NUMBER,
    CONF_WEEKDAY_ORDER_NUMBER,
    DAILY_BLANK_FREQUENCY,
    DOMAIN,
    GROUP_FREQUENCY,
    MONTHLY_FREQUENCY,
)

_LOGGER = logging.getLogger(__name__)


class GarbageCollectionShared:
    """Store configuration for both YAML and config_flow."""

    def __init__(self, unique_id):
        """Create class attributes and set initial values."""
        self._data = {}
        self._data["unique_id"] = unique_id
        self.name = None
        self.errors = {}
        self.data_schema = {}

    def update_data(self, user_input: Dict, step: int):
        """Remove empty fields, and fields that should not be stored in the config."""
        self._data.update(user_input)
        items = {
            key: value
            for (key, value) in config_definition.options.items()
            if ("step" in value and value["step"] == step)
        }
        for key in items:
            if key in self._data and (key not in user_input or user_input[key] == ""):
                del self._data[key]
        if CONF_NAME in self._data:
            self.name = self._data[CONF_NAME]
            del self._data[CONF_NAME]

    def step1_user_init(self, user_input: Dict, defaults=None):
        """Step 1 - general set-up."""
        self.errors = {}
        if user_input is not None:
            validation = config_definition.compile_schema(step=1)
            if CONF_INCLUDE_DATES in user_input:
                user_input[CONF_INCLUDE_DATES] = string_to_list(
                    user_input[CONF_INCLUDE_DATES]
                )
            if CONF_EXCLUDE_DATES in user_input:
                user_input[CONF_EXCLUDE_DATES] = string_to_list(
                    user_input[CONF_EXCLUDE_DATES]
                )
            # Name is not used in OptionsFlow
            if defaults is not None and CONF_NAME in validation:
                del validation[CONF_NAME]
            try:
                _ = vol.Schema(validation, extra=vol.ALLOW_EXTRA)(user_input)
            except vol.Invalid as exception:
                _LOGGER.debug("Config flow error (step1): %s", exception)
                error = str(exception)
                if (
                    CONF_INCLUDE_DATES in error
                    or CONF_EXCLUDE_DATES in error
                    or CONF_FIRST_DATE in error
                ):
                    self.errors["base"] = "date"
                elif (
                    CONF_ICON_NORMAL in error
                    or CONF_ICON_TODAY in error
                    or CONF_ICON_TOMORROW in error
                ):
                    self.errors["base"] = "icon"
                elif CONF_EXPIRE_AFTER in error:
                    self.errors["base"] = "time"
                else:
                    _LOGGER.error("Unknown exception: %s", exception)
                    self.errors["base"] = "value"
                config_definition.set_defaults(1, user_input)
            if self.errors == {}:
                # Valid input - go to the next step!
                self.update_data(user_input, 1)
                return True
        elif defaults is not None:
            config_definition.reset_defaults()
            config_definition.set_defaults(1, defaults)
            config_definition.join_list(CONF_EXCLUDE_DATES)
            config_definition.join_list(CONF_INCLUDE_DATES)
        self.data_schema = config_definition.compile_config_flow(step=1)
        # Do not show name for Options_Flow. The name cannot be changed here
        if defaults is not None and CONF_NAME in self.data_schema:
            del self.data_schema[CONF_NAME]
        return False

    def step2_annual_group(self, user_input: Dict, defaults=None):
        """Step 2 - Annual or Group (no week days)."""
        self.errors = {}
        self.data_schema = {}
        updates = {}
        if user_input is not None and user_input != {}:
            validation = vol.Schema(
                config_definition.compile_schema(
                    step=2, valid_for=self._data[CONF_FREQUENCY]
                ),
                extra=vol.ALLOW_EXTRA,
            )
            try:
                updates = validation(user_input)
            except vol.Invalid as exception:
                _LOGGER.debug("Config flow error (step2): %s", exception)
                if self._data[CONF_FREQUENCY] in ANNUAL_FREQUENCY:
                    self.errors["base"] = "month_day"
                else:
                    self.errors["base"] = "entities"
                config_definition.set_defaults(2, user_input)
            if self.errors == {}:
                # Remember step2 values
                if self._data[CONF_FREQUENCY] in GROUP_FREQUENCY:
                    updates[CONF_ENTITIES] = string_to_list(user_input[CONF_ENTITIES])
                self.update_data(updates, 2)
                return True
        elif defaults is not None:
            config_definition.set_defaults(2, defaults)
        self.data_schema = config_definition.compile_config_flow(
            step=2, valid_for=self._data[CONF_FREQUENCY]
        )
        return False

    def step3_detail(self, user_input: Dict, defaults=None):
        """Step 2 - other than Annual or Group."""
        self.errors = {}
        self.data_schema = {}
        if user_input is not None and user_input != {}:
            updates = user_input.copy()
            days_to_list(updates)
            validation_schema = config_definition.compile_schema(
                step=3, valid_for=self._data[CONF_FREQUENCY]
            )
            if self._data[CONF_FREQUENCY] in MONTHLY_FREQUENCY:
                validation_schema[
                    vol.Optional(CONF_FORCE_WEEK_NUMBERS, default=False)
                ] = cv.boolean
            validation = vol.Schema(validation_schema, extra=vol.ALLOW_EXTRA)
            try:
                updates = validation(updates)
            except vol.Invalid as exception:
                _LOGGER.debug("Config flow error (step2): %s", exception)
                self.errors["base"] = "value"
            if len(updates[CONF_COLLECTION_DAYS]) == 0:
                self.errors["base"] = "days"
            if self.errors == {}:
                # Remember values
                self.update_data(updates, 3)
                return True
        elif defaults is not None:
            config_definition.set_defaults(3, defaults)
        self.data_schema = config_definition.compile_config_flow(
            step=3, valid_for=self._data[CONF_FREQUENCY]
        )
        list_to_days(self.data_schema)
        if self._data[CONF_FREQUENCY] in MONTHLY_FREQUENCY:
            if user_input is not None and CONF_FORCE_WEEK_NUMBERS in user_input:
                force_week_numbers = user_input[CONF_FORCE_WEEK_NUMBERS]
            elif defaults is not None and CONF_WEEK_ORDER_NUMBER in defaults:
                force_week_numbers = True
            else:
                force_week_numbers = False
            self.data_schema[
                vol.Optional(CONF_FORCE_WEEK_NUMBERS, default=force_week_numbers)
            ] = bool
        return False

    def step4_final(self, user_input: Dict, defaults=None):
        """Step 3 - additional parameters."""
        self.errors = {}
        self.data_schema = {}
        if user_input is not None and user_input != {}:
            updates = user_input.copy()
            if self._data[CONF_FREQUENCY] in MONTHLY_FREQUENCY:
                if self._data[CONF_FORCE_WEEK_NUMBERS]:
                    weekdays_to_list(updates, CONF_WEEK_ORDER_NUMBER)
                else:
                    weekdays_to_list(updates, CONF_WEEKDAY_ORDER_NUMBER)
            validation = vol.Schema(
                config_definition.compile_schema(
                    step=4, valid_for=self._data[CONF_FREQUENCY]
                ),
                extra=vol.ALLOW_EXTRA,
            )
            if CONF_HOLIDAY_POP_NAMED in updates:
                updates[CONF_HOLIDAY_POP_NAMED] = string_to_list(
                    updates[CONF_HOLIDAY_POP_NAMED]
                )
            try:
                updates = validation(updates)
            except vol.Invalid as exception:
                _LOGGER.debug("Config flow error (step3): %s", exception)
                self.errors["base"] = "value"
            if self._data[CONF_FREQUENCY] in MONTHLY_FREQUENCY:
                if self._data[CONF_FORCE_WEEK_NUMBERS]:
                    if len(updates[CONF_WEEK_ORDER_NUMBER]) == 0:
                        self.errors["base"] = CONF_WEEK_ORDER_NUMBER
                else:
                    if len(updates[CONF_WEEKDAY_ORDER_NUMBER]) == 0:
                        self.errors["base"] = CONF_WEEKDAY_ORDER_NUMBER
            if self.errors == {}:
                self.update_data(updates, 4)
                if CONF_FORCE_WEEK_NUMBERS in self._data:
                    if self._data[CONF_FORCE_WEEK_NUMBERS]:
                        if CONF_WEEKDAY_ORDER_NUMBER in self._data:
                            del self._data[CONF_WEEKDAY_ORDER_NUMBER]
                    else:
                        if CONF_WEEK_ORDER_NUMBER in self._data:
                            del self._data[CONF_WEEK_ORDER_NUMBER]
                    del self._data[CONF_FORCE_WEEK_NUMBERS]
                if CONF_NAME in self._data:
                    del self._data[CONF_NAME]
                return True
        elif defaults is not None:
            config_definition.set_defaults(4, defaults)
            config_definition.join_list(CONF_HOLIDAY_POP_NAMED)
        self.data_schema = config_definition.compile_config_flow(
            step=4, valid_for=self._data[CONF_FREQUENCY]
        )
        if self._data[CONF_FREQUENCY] in MONTHLY_FREQUENCY:
            if self._data[CONF_FORCE_WEEK_NUMBERS]:
                list_to_weekdays(self.data_schema, CONF_WEEK_ORDER_NUMBER)
            else:
                list_to_weekdays(self.data_schema, CONF_WEEKDAY_ORDER_NUMBER)
        return False

    @property
    def frequency(self):
        """Return the collection frequency."""
        try:
            return self._data[CONF_FREQUENCY]
        except KeyError:
            return None

    @property
    def data(self):
        """Return whole data store."""
        return self._data


@config_entries.HANDLERS.register(DOMAIN)
class GarbageCollectionFlowHandler(config_entries.ConfigFlow):
    """Config flow for garbage_collection."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize."""
        config_definition.reset_defaults()
        self._import = {}
        self.shared_class = GarbageCollectionShared(str(uuid.uuid4()))

    async def async_step_user(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 1 - general parameters."""
        next_step = self.shared_class.step1_user_init(user_input)
        if next_step:
            if self.shared_class.frequency in ANNUAL_GROUP_FREQUENCY:
                return await self.async_step_annual_group(self._import)
            if self.shared_class.frequency in DAILY_BLANK_FREQUENCY:
                return await self.async_step_final(self._import)
            return await self.async_step_detail(self._import)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                self.shared_class.data_schema, extra=vol.ALLOW_EXTRA
            ),
            errors=self.shared_class.errors,
        )

    async def async_step_annual_group(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 2 - annual or group (no week days)."""
        next_step = self.shared_class.step2_annual_group(user_input, self._import)
        if next_step:
            return self.async_create_entry(
                title=self.shared_class.name, data=self.shared_class.data
            )
        return self.async_show_form(
            step_id="annual_group",
            data_schema=vol.Schema(
                self.shared_class.data_schema, extra=vol.ALLOW_EXTRA
            ),
            errors=self.shared_class.errors,
        )

    async def async_step_detail(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 2 - other than annual or group."""
        next_step = self.shared_class.step3_detail(user_input, self._import)
        if next_step:
            return await self.async_step_final(self._import)
        else:
            return self.async_show_form(
                step_id="detail",
                data_schema=vol.Schema(
                    self.shared_class.data_schema, extra=vol.ALLOW_EXTRA
                ),
                errors=self.shared_class.errors,
            )

    async def async_step_final(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 3 - additional parameters."""
        if self.shared_class.step4_final(user_input, self._import):
            return self.async_create_entry(
                title=self.shared_class.name, data=self.shared_class.data
            )
        return self.async_show_form(
            step_id="final",
            data_schema=vol.Schema(
                self.shared_class.data_schema, extra=vol.ALLOW_EXTRA
            ),
            errors=self.shared_class.errors,
        )

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import config from configuration.yaml."""
        _LOGGER.debug("Importing config for %s", user_input)
        self._import = user_input
        return await self.async_step_user(self._import)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return options flow handler, or empty options flow if no unique_id."""
        if config_entry.data.get("unique_id", None) is not None:
            return OptionsFlowHandler(config_entry)
        return EmptyOptions(config_entry)


"""


O P T I O N S   F L O W


"""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler."""

    def __init__(self, config_entry):
        """Create and initualize class variables."""
        self.config_entry = config_entry
        self.shared_class = GarbageCollectionShared(config_entry.data.get("unique_id"))

    async def async_step_init(self, user_input=None):
        """Genral parameters."""
        next_step = self.shared_class.step1_user_init(
            user_input, self.config_entry.data
        )
        if next_step:
            if self.shared_class.frequency in ANNUAL_GROUP_FREQUENCY:
                return await self.async_step_annual_group()
            elif self.shared_class.frequency in DAILY_BLANK_FREQUENCY:
                return await self.async_step_final()
            else:
                return await self.async_step_detail()
        else:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(self.shared_class.data_schema),
                errors=self.shared_class.errors,
            )

    async def async_step_annual_group(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 2 - annual or group (no week days)."""
        next_step = self.shared_class.step2_annual_group(
            user_input, self.config_entry.data
        )
        if next_step:
            return self.async_create_entry(title="", data=self.shared_class.data)
        else:
            return self.async_show_form(
                step_id="annual_group",
                data_schema=vol.Schema(self.shared_class.data_schema),
                errors=self.shared_class.errors,
            )

    async def async_step_detail(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 2 - other than annual or group."""
        next_step = self.shared_class.step3_detail(user_input, self.config_entry.data)
        if next_step:
            return await self.async_step_final()
        else:
            return self.async_show_form(
                step_id="detail",
                data_schema=vol.Schema(self.shared_class.data_schema),
                errors=self.shared_class.errors,
            )

    async def async_step_final(
        self, user_input={}
    ):  # pylint: disable=dangerous-default-value
        """Step 3 - additional parameters."""
        if self.shared_class.step4_final(user_input, self.config_entry.data):
            return self.async_create_entry(title="", data=self.shared_class.data)
        else:
            return self.async_show_form(
                step_id="final",
                data_schema=vol.Schema(self.shared_class.data_schema),
                errors=self.shared_class.errors,
            )


class EmptyOptions(config_entries.OptionsFlow):
    """A class for default options. Not sure why this is required."""

    def __init__(self, config_entry):
        """Just set the config_entry parameter."""
        self.config_entry = config_entry


def is_month_day(date) -> bool:
    """Validate mm/dd format."""
    try:
        date = datetime.strptime(date, "%m/%d")
        return True
    except ValueError:
        return False


def is_date(date) -> bool:
    """Validate yyyy-mm-dd format."""
    if date == "":
        return True
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def string_to_list(string) -> list:
    """Convert comma separated text to list."""
    if isinstance(string, list):
        return string  # Already list
    if string is None or string == "":
        return []
    return list(map(lambda x: x.strip("'\" "), string.split(",")))


def days_to_list(src):
    """Compile a list of days from individual variables."""
    if CONF_COLLECTION_DAYS in src:
        return  # Already list
    src[CONF_COLLECTION_DAYS] = []
    for day in WEEKDAYS:
        if src[f"collection_days_{day.lower()}"]:
            src[CONF_COLLECTION_DAYS].append(day)
        del src[f"collection_days_{day.lower()}"]


def weekdays_to_list(src, prefix):
    """Compile a list of weekdays from individual variables."""
    if prefix in src:
        return  # Already list
    src[prefix] = []
    for i in range(5):
        if src[f"{prefix}_{i+1}"]:
            src[prefix].append(i + 1)
        del src[f"{prefix}_{i+1}"]


def list_to_days(data_schema):
    """Create variables back from the list."""
    copy = data_schema.copy()
    data_schema.clear()
    for day in WEEKDAYS:
        data_schema[
            vol.Required(
                f"collection_days_{day.lower()}",
                default=bool(
                    CONF_COLLECTION_DAYS in config_definition.defaults
                    and day in config_definition.defaults[CONF_COLLECTION_DAYS]
                ),
            )
        ] = bool
    items = {
        key: value for (key, value) in copy.items() if key not in [CONF_COLLECTION_DAYS]
    }
    for key, value in items.items():
        data_schema[key] = value


def list_to_weekdays(data_schema, prefix):
    """Create variables back from the list."""
    copy = data_schema.copy()
    data_schema.clear()
    for i in range(5):
        data_schema[
            vol.Required(
                f"{prefix}_{i+1}",
                default=bool(
                    prefix in config_definition.defaults
                    and (i + 1) in config_definition.defaults[prefix]
                ),
            )
        ] = bool
    items = {
        key: value
        for (key, value) in copy.items()
        if key not in [CONF_WEEKDAY_ORDER_NUMBER, CONF_WEEK_ORDER_NUMBER]
    }
    for key, value in items.items():
        data_schema[key] = value


def is_dates(dates) -> bool:
    """Validate list of dates (yyyy-mm-dd, yyyy-mm-dd)."""
    if dates == []:
        return True
    check = True
    for date in dates:
        if not is_date(date):
            check = False
    return check
