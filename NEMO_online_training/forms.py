from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from NEMO_online_training.models import OnlineUserTraining, ProspectiveUser


# Using non-underscore fields here since django Forms don't like variables starting with _
class ProspectiveUserForm(forms.ModelForm):
    first_name = forms.CharField(label="First name", required=True)
    last_name = forms.CharField(label="Last name", required=True)
    email = forms.EmailField(label="Email", required=True)

    class Meta:
        model = ProspectiveUser
        exclude = ["_first_name", "_last_name", "_email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance._first_name
            self.fields["last_name"].initial = self.instance._last_name
            self.fields["email"].initial = self.instance._email

    def clean(self):
        cleaned_data = super().clean()
        self.instance._first_name = cleaned_data.get("first_name", "").strip()
        self.instance._last_name = cleaned_data.get("last_name", "").strip()
        self.instance._email = cleaned_data.get("email", "").strip()
        return cleaned_data


class OnlineUserTrainingForm(forms.ModelForm):
    class Meta:
        model = OnlineUserTraining
        fields = ["due_date"]

    def clean_due_date(self):
        due_date = self.cleaned_data.get("due_date")
        if due_date and due_date < timezone.now():
            raise ValidationError(_("Due date must be in the future."))
        return due_date
