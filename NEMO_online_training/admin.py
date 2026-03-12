from NEMO.actions import has_perm
from NEMO.typing import QuerySetType
from NEMO.utilities import new_model_copy
from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.safestring import mark_safe

from NEMO_online_training.models import OnlineTraining, OnlineTrainingAction, OnlineUserTraining, ProspectiveUser
from NEMO_online_training.training_actions import action_handlers


@admin.action(description="Duplicate selected training")
def duplicate_online_training(model_admin, request, queryset: QuerySetType[OnlineTraining]):
    if not has_perm(request, queryset, "add") or not has_perm(request, queryset, "change"):
        model_admin.message_user(request, "You do not have permission to run this action.", level=messages.ERROR)
    for online_training in queryset:
        original_name = online_training.name
        new_name = "Copy of " + online_training.name
        try:
            if OnlineTraining.objects.filter(name=new_name).exists():
                messages.error(
                    request,
                    mark_safe(
                        f'There is already a copy of {original_name} as <a href="{reverse("admin:NEMO_online_training_onlinetraining_change", args=[online_training.id])}">{new_name}</a>. Change the copy\'s name and try again'
                    ),
                )
                continue
            else:
                old_actions = online_training.onlinetrainingaction_set.all()
                new_online_training = new_model_copy(online_training)
                new_online_training.name = new_name
                new_online_training.save()
                for action in old_actions:
                    new_online_training.onlinetrainingaction_set.add(action)
                messages.success(
                    request,
                    mark_safe(
                        f'A duplicate of {original_name} has been made as <a href="{reverse("admin:NEMO_online_training_onlinetraining_change", args=[new_online_training.id])}">{new_online_training.name}</a>'
                    ),
                )
        except Exception as error:
            messages.error(
                request, f"{original_name} could not be duplicated because of the following error: {str(error)}"
            )


@admin.register(ProspectiveUser)
class ProspectiveUserAdmin(admin.ModelAdmin):
    list_display = [
        "first_name",
        "last_name",
        "email",
        "get_all_blocking_trainings_completed",
        "get_all_trainings_completed",
        "last_accessed",
        "creation_time",
        "id",
    ]
    date_hierarchy = "creation_time"
    autocomplete_fields = ["nemo_user"]
    readonly_fields = ["creation_time", "last_updated", "last_accessed"]

    @admin.display(boolean=True, description="All Trainings Completed")
    def get_all_trainings_completed(self, obj: ProspectiveUser) -> bool:
        return obj.all_trainings_completed()

    @admin.display(boolean=True, description="All Blocking Trainings Completed")
    def get_all_blocking_trainings_completed(self, obj: ProspectiveUser) -> bool:
        return obj.all_blocking_trainings_completed()


class OnlineTrainingActionInlineForm(forms.ModelForm):
    action_type = forms.ChoiceField(choices=[])  # Start empty

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["action_type"].choices = [(action.name, action.description) for action in action_handlers.values()]

    class Meta:
        model = OnlineTrainingAction
        fields = "__all__"


class OnlineTrainingActionInline(admin.TabularInline):
    model = OnlineTrainingAction
    extra = 0
    verbose_name = "After training is completed"
    verbose_name_plural = "After training is completed"
    form = OnlineTrainingActionInlineForm


@admin.register(OnlineTraining)
class OnlineTrainingAdmin(admin.ModelAdmin):
    inlines = [OnlineTrainingActionInline]
    list_display = ["name", "enabled", "is_blocking", "completion_time_limit", "creation_time", "id"]
    date_hierarchy = "creation_time"
    list_filter = ["enabled", "is_blocking"]
    actions = [duplicate_online_training]


@admin.register(OnlineUserTraining)
class OnlineUserTrainingAdmin(admin.ModelAdmin):
    list_display = [
        "prospective_user",
        "online_training",
        "get_training_completed",
        "get_training_expired",
        "due_date",
        "completion_time",
        "start",
        "end",
        "creation_time",
        "last_updated",
        "id",
    ]
    list_filter = ["online_training"]
    date_hierarchy = "creation_time"
    readonly_fields = ["creation_time", "last_updated"]

    @admin.display(boolean=True, description="Completed")
    def get_training_completed(self, obj: OnlineUserTraining) -> bool:
        return obj.completed()

    @admin.display(boolean=True, description="Expired")
    def get_training_expired(self, obj: OnlineUserTraining) -> bool:
        return obj.has_training_expired()
