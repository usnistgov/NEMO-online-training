from NEMO.serializers import ModelSerializer
from NEMO.views.api import ModelViewSet, boolean_filters, datetime_filters, key_filters, number_filters, string_filters
from rest_flex_fields.serializers import FlexFieldsSerializerMixin

from NEMO_online_training.models import OnlineTraining, OnlineTrainingAction, OnlineUserTraining, ProspectiveUser


class OnlineTrainingSerializer(ModelSerializer):
    class Meta:
        model = OnlineTraining
        fields = "__all__"


class ProspectiveUserSerializer(FlexFieldsSerializerMixin, ModelSerializer):
    class Meta:
        model = ProspectiveUser
        fields = "__all__"
        expandable_fields = {
            "nemo_user": "NEMO.serializers.UserSerializer",
        }


class OnlineUserTrainingSerializer(FlexFieldsSerializerMixin, ModelSerializer):
    class Meta:
        model = OnlineUserTraining
        fields = "__all__"
        expandable_fields = {
            "online_training": "NEMO_online_training.api.OnlineTrainingSerializer",
            "prospective_user": "NEMO_online_training.api.ProspectiveUserSerializer",
        }


class OnlineTrainingActionSerializer(FlexFieldsSerializerMixin, ModelSerializer):
    class Meta:
        model = OnlineTrainingAction
        fields = "__all__"
        expandable_fields = {
            "online_training": "NEMO_online_training.api.OnlineTrainingSerializer",
        }


class OnlineTrainingViewSet(ModelViewSet):
    filename = "online_trainings"
    queryset = OnlineTraining.objects.all()
    serializer_class = OnlineTrainingSerializer
    filterset_fields = {
        "id": key_filters,
        "name": string_filters,
        "enabled": boolean_filters,
        "completion_time_limit": number_filters,
        "is_blocking": boolean_filters,
        "allow_self_enrollment": boolean_filters,
        "html_content": string_filters,
        "creation_time": datetime_filters,
    }


class ProspectiveUserViewSet(ModelViewSet):
    filename = "prospective_users"
    queryset = ProspectiveUser.objects.all()
    serializer_class = ProspectiveUserSerializer
    filterset_fields = {
        "id": key_filters,
        "creation_time": datetime_filters,
        "last_updated": datetime_filters,
        "last_accessed": datetime_filters,
        "_first_name": string_filters,
        "_last_name": string_filters,
        "_email": string_filters,
        "nemo_user": key_filters,
    }


class OnlineUserTrainingViewSet(ModelViewSet):
    filename = "online_user_trainings"
    queryset = OnlineUserTraining.objects.all()
    serializer_class = OnlineUserTrainingSerializer
    filterset_fields = {
        "id": key_filters,
        "online_training": key_filters,
        "prospective_user": key_filters,
        "due_date": datetime_filters,
        "start": datetime_filters,
        "end": datetime_filters,
        "completion_data": [],
        "creation_time": datetime_filters,
        "last_updated": datetime_filters,
    }


class OnlineTrainingActionViewSet(ModelViewSet):
    filename = "online_training_actions"
    queryset = OnlineTrainingAction.objects.all()
    serializer_class = OnlineTrainingActionSerializer
    filterset_fields = {
        "id": key_filters,
        "online_training": key_filters,
        "action_type": string_filters,
        "configuration": [],
        "user_filter": string_filters,
    }
