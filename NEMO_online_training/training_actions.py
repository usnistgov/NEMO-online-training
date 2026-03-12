from abc import ABC, abstractmethod
from typing import Dict

from NEMO.utilities import render_email_template
from NEMO.views.customization import ApplicationCustomization
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from NEMO_online_training.fields import UserTypeFilterField
from NEMO_online_training.utilities import (
    ONLINE_TRAINING_ACTION_EXTEND_ACCESS,
    ONLINE_TRAINING_ACTION_REMOVE_TRAINING_REQUIRED,
    ONLINE_TRAINING_ACTION_SEND_EMAIL,
)


class OnlineTrainingActionHandler(ABC):
    """
    Base class for all online training action handlers.
    Similar to NEMO's interlock pattern.
    """

    @abstractmethod
    def validate(self, configuration: dict, user_filter: list[str]):
        """
        Validate the action configuration and user filter.
        Raise ValidationError if the configuration or user filter is invalid.

        Args:
            configuration: The JSON configuration dict from OnlineTrainingAction
            user_filter: The list of user types to apply the action to
        """
        if not isinstance(configuration, dict):
            raise ValidationError(_("Configuration must be a dictionary"))

    def perform(self, action, user_training) -> None:
        if action.applies_to_user(user_training.prospective_user):
            self.do_perform(action, user_training)

    @abstractmethod
    def do_perform(self, action, user_training) -> None:
        """
        Perform the action.

        Args:
            action: The OnlineTrainingAction
            user_training: The OnlineUserTraining
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the name of the action to be saved in the database.
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Return a description of the action to be shown to the user.
        """
        pass


class ExtendAccessOnlineTrainingHandler(OnlineTrainingActionHandler):
    """Handler for extending user access expiration"""

    @property
    def name(self) -> str:
        return ONLINE_TRAINING_ACTION_EXTEND_ACCESS

    @property
    def description(self) -> str:
        return _("Extend User Access Expiration")

    def validate(self, configuration: dict, user_filter: list[str]) -> None:
        super().validate(configuration, user_filter)

        if UserTypeFilterField.PROSPECTIVE_USERS in user_filter:
            raise ValidationError({"user_filter": _("New users cannot have their access extended")})

        if "extend_by_days" not in configuration:
            raise ValidationError({"configuration": _("Configuration must include 'extend_by_days' field")})

        extend_by_days = configuration.get("extend_by_days")
        if not isinstance(extend_by_days, (int, float)) or extend_by_days <= 0:
            raise ValidationError({"configuration": _("'extend_by_days' must be a positive number")})

    def do_perform(self, action, user_training) -> None:
        from datetime import timedelta
        from django.utils import timezone

        extend_by_days = action.configuration["extend_by_days"]

        # If the user is linked to a NEMO user
        if user_training.prospective_user.nemo_user:
            nemo_user = user_training.prospective_user.nemo_user
            current_expiration = nemo_user.access_expiration or timezone.now()
            nemo_user.access_expiration = current_expiration + timedelta(days=extend_by_days)
            nemo_user.save(update_fields=["access_expiration"])


class RemoveTrainingRequiredOnlineTrainingHandler(OnlineTrainingActionHandler):
    """Handler for removing training requirement on user"""

    @property
    def name(self) -> str:
        return ONLINE_TRAINING_ACTION_REMOVE_TRAINING_REQUIRED

    @property
    def description(self) -> str:
        return _("Remove training required on user account")

    def validate(self, configuration: dict, user_filter: list[str]) -> None:
        super().validate(configuration, user_filter)

        if UserTypeFilterField.PROSPECTIVE_USERS in user_filter:
            raise ValidationError(
                {
                    "user_filter": _(
                        f"New users cannot have their {ApplicationCustomization.get('facility_rules_name')} requirement removed"
                    )
                }
            )

    def do_perform(self, action, user_training) -> None:
        # If the user is linked to a NEMO user and has training required
        if user_training.prospective_user.nemo_user and user_training.online_training.training_required:
            nemo_user = user_training.prospective_user.nemo_user
            nemo_user.training_required = False
            nemo_user.save(update_fields=["training_required"])


class SendEmailOnlineTrainingHandler(OnlineTrainingActionHandler):
    """Handler for sending notification emails"""

    @property
    def name(self) -> str:
        return ONLINE_TRAINING_ACTION_SEND_EMAIL

    @property
    def description(self) -> str:
        return _("Send Notification Email")

    def validate(self, configuration: dict, user_filter: list) -> None:
        super().validate(configuration, user_filter)

        if "subject" not in configuration:
            raise ValidationError({"configuration": _("Configuration must include 'subject' field")})

        if "message" not in configuration:
            raise ValidationError({"configuration": _("Configuration must include 'message' field")})

        if "recipients" not in configuration:
            raise ValidationError({"configuration": _("Configuration must include 'recipients' field")})

        recipients = configuration.get("recipients")
        if not isinstance(recipients, list) or not recipients:
            raise ValidationError({"configuration": _("'recipients' must be a non-empty list")})

        valid_recipient_types = ["user"]
        for recipient in recipients:
            if not isinstance(recipient, str):
                raise ValidationError({"configuration": _("Each recipient must be a string")})
            # Check if it's a valid type or an email
            if recipient not in valid_recipient_types and "@" not in recipient:
                raise ValidationError(
                    {"configuration": _(f"Invalid recipient '{recipient}'. Must be 'user', or a valid email address")}
                )

    def do_perform(self, action, user_training) -> None:
        from NEMO.utilities import send_mail

        from NEMO_online_training.utilities import ONLINE_TRAINING_EMAIL_CATEGORY

        subject = action.configuration["subject"]
        message = action.configuration["message"]
        recipients = action.configuration["recipients"]

        # Format message with available context
        context = {
            "training_user": user_training.prospective_user,
            "training": user_training.online_training,
            "record": user_training,
            "action": action,
        }
        formatted_message = render_email_template(message, context)
        formatted_subject = render_email_template(subject, context)

        # Build recipient list
        recipient_emails = []
        for recipient in recipients:
            if recipient == "user":
                recipient_emails.append(user_training.prospective_user.email)
            else:
                # Assume it's an email address
                recipient_emails.append(recipient)

        if recipient_emails:
            send_mail(
                formatted_subject,
                formatted_message,
                from_email=None,
                to=recipient_emails,
                email_category=ONLINE_TRAINING_EMAIL_CATEGORY,
            )


# Registry of all action handlers
action_handlers: Dict[str, OnlineTrainingActionHandler] = {
    ONLINE_TRAINING_ACTION_EXTEND_ACCESS: ExtendAccessOnlineTrainingHandler(),
    ONLINE_TRAINING_ACTION_REMOVE_TRAINING_REQUIRED: RemoveTrainingRequiredOnlineTrainingHandler(),
    ONLINE_TRAINING_ACTION_SEND_EMAIL: SendEmailOnlineTrainingHandler(),
}
