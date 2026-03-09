from typing import List, Optional, Tuple, Union

from NEMO.exceptions import NEMOException, ProjectChargeException, UserAccessError
from NEMO.models import (
    Area,
    AreaAccessRecord,
    Consumable,
    ConsumableWithdraw,
    Project,
    Reservation,
    StaffCharge,
    Tool,
    UsageEvent,
    User,
)
from NEMO.policy import BaseNEMOPolicy
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.safestring import mark_safe

from NEMO_online_training.models import OnlineUserTraining, ProspectiveUser


class BlockingTrainingDueException(NEMOException):
    pass


class ProjectBlockingTrainingDueException(ProjectChargeException):
    pass


class AccessBlockingTrainingDueException(UserAccessError):
    pass


class NEMOOnlineTrainingPolicy(BaseNEMOPolicy):

    def check_to_save_reservation(
        self,
        cancelled_reservation: Optional[Reservation],
        new_reservation: Reservation,
        user_creating_reservation: User,
        explicit_policy_override: bool,
    ) -> Tuple[List[str], bool]:
        policy_problems = []

        if new_reservation.user.is_staff_on_tool(new_reservation.tool) or explicit_policy_override:
            return policy_problems, False

        prospective_user = ProspectiveUser.objects.filter(nemo_user=new_reservation.user).first()
        if prospective_user and not prospective_user.all_blocking_trainings_completed():
            msg = get_blocking_training_error_message(prospective_user.all_blocking_trainings_due())
            policy_problems.append(msg)
            return policy_problems, True

        return policy_problems, True

    def check_to_enable_tool(
        self, tool: Tool, operator: User, user: User, project: Project, staff_charge: bool, remote_work=False
    ) -> HttpResponse:
        if not operator.is_staff_on_tool(tool):
            prospective_user = ProspectiveUser.objects.filter(nemo_user=user).first()
            if prospective_user and not prospective_user.all_blocking_trainings_completed():
                msg = get_blocking_training_error_message(prospective_user.all_blocking_trainings_due())
                return HttpResponseBadRequest(msg)
        return HttpResponse()

    def check_to_enter_any_area(self, user: User):
        prospective_user = ProspectiveUser.objects.filter(nemo_user=user).first()
        if prospective_user and not prospective_user.all_blocking_trainings_completed():
            msg = get_blocking_training_error_message(prospective_user.all_blocking_trainings_due(), html=False)
            raise AccessBlockingTrainingDueException(msg)

    def check_billing_to_project(
        self,
        project: Project,
        user: User,
        item: Union[Tool, Area, Consumable, StaffCharge] = None,
        charge: Union[UsageEvent, AreaAccessRecord, ConsumableWithdraw, StaffCharge, Reservation] = None,
    ):
        if not isinstance(charge, (Reservation, UsageEvent, AreaAccessRecord)):
            prospective_user = ProspectiveUser.objects.filter(nemo_user=user).first()
            if prospective_user and not prospective_user.all_blocking_trainings_completed():
                msg = get_blocking_training_error_message(prospective_user.all_blocking_trainings_due())
                raise ProjectBlockingTrainingDueException(project=project, user=user, msg=msg)


def get_blocking_training_error_message(user_trainings_due: QuerySet[OnlineUserTraining], html=True) -> str:
    training_names = user_trainings_due.values_list("online_training__name", flat=True)
    training_list = ""
    if html:
        for training in training_names:
            training_list += f"<li style='margin-left: 40px'>{training}</li>"
        return mark_safe(
            f"<ul style='padding-left:0'>The following trainings must be completed before proceeding: {training_list}</ul>"
        )
    else:
        return f"The following trainings must be completed before proceeding: {', '.join(training_names)}"
