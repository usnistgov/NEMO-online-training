from django.apps import AppConfig
from django.conf import settings


class OnlineTrainingConfig(AppConfig):
    name = "NEMO_online_training"
    verbose_name = "online training"
    plugin_id = 2200
    default_auto_field = "django.db.models.AutoField"

    @classmethod
    def get_plugin_id(cls):
        # Used to make EmailCategory and other IntegerChoices ranges unique
        return getattr(settings, f"{cls.name.upper()}_PLUGIN_ID", cls.plugin_id)

    def ready(self):
        from django.utils.translation import gettext_lazy as _
        from NEMO.plugins.utils import (
            add_dynamic_email_categories,
            add_dynamic_notification_types,
            add_extra_policy_class,
            check_extra_dependencies,
        )
        from NEMO_online_training.utilities import (
            ONLINE_TRAINING_EMAIL_CATEGORY,
            ONLINE_TRAINING_NOTIFICATION_TYPE,
        )
        from NEMO_online_training.policy import NEMOOnlineTrainingPolicy

        check_extra_dependencies(self.name, ["NEMO", "NEMO-CE"])

        add_dynamic_email_categories([(ONLINE_TRAINING_EMAIL_CATEGORY, _("Online training"))])
        add_dynamic_notification_types(
            [(ONLINE_TRAINING_NOTIFICATION_TYPE, "New online trainings - notifies users with pending trainings")]
        )
        add_extra_policy_class(f"{NEMOOnlineTrainingPolicy.__module__}.{NEMOOnlineTrainingPolicy.__qualname__}")
