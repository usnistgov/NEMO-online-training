from django.contrib import admin

from NEMO_online_training.models import OnlineTraining, OnlineTrainingAction, OnlineUserTraining, ProspectiveUser


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
    readonly_fields = ["creation_time", "last_updated", "last_accessed"]

    @admin.display(boolean=True, description="All Trainings Completed")
    def get_all_trainings_completed(self, obj: ProspectiveUser) -> bool:
        return obj.all_trainings_completed()

    @admin.display(boolean=True, description="All Blocking Trainings Completed")
    def get_all_blocking_trainings_completed(self, obj: ProspectiveUser) -> bool:
        return obj.all_blocking_trainings_completed()


class OnlineTrainingActionInline(admin.StackedInline):
    model = OnlineTrainingAction
    extra = 0


@admin.register(OnlineTraining)
class OnlineTrainingAdmin(admin.ModelAdmin):
    inlines = [OnlineTrainingActionInline]
    list_display = ["name", "enabled", "is_blocking", "completion_time_limit", "creation_time", "id"]
    date_hierarchy = "creation_time"
    list_filter = ["enabled", "is_blocking"]


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
