import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import CONF_MPRN, CONF_PASSWORD, CONF_USERNAME, DOMAIN, NAME


class ESBSmartMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_MPRN])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_MPRN, description={"suggested_value": ""}): str,
            }),
            description_placeholders={"mprn_help": "11-digit MPRN from your ESB Networks account"},
            errors=errors,
        )
