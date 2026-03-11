import json
from datetime import timedelta
from logging import getLogger
from typing import Optional

from NEMO.decorators import user_office_or_manager_required
from NEMO.models import User
from NEMO.utilities import format_datetime, queryset_search_filter, render_email_template
from NEMO.views.pagination import SortedPaginator
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from NEMO_online_training.customization import OnlineTrainingCustomization
from NEMO_online_training.forms import OnlineUserTrainingForm, ProspectiveUserForm
from NEMO_online_training.models import OnlineTraining, OnlineUserTraining, ProspectiveUser

online_training_logger = getLogger(__name__)


@login_required
@require_GET
def user_online_trainings(request, prospective_user_id=None):
    user: User = request.user
    selected_status = request.GET.get("training_status", "")
    selected_user_type = request.GET.get("user_type", "")

    current_user_trainings = False
    single_user_view = False

    user_is_staff = user.is_user_office or user.is_facility_manager or user.is_superuser

    prospective_users = ProspectiveUser.objects_with_trainings()
    if not user_is_staff:
        current_user_trainings = True
        single_user_view = True
        prospective_users = prospective_users.filter(nemo_user=user)
    elif prospective_user_id:
        single_user_view = True
        prospective_users = prospective_users.filter(id=prospective_user_id)

    if selected_status == "complete":
        prospective_users = prospective_users.filter(all_trainings_completed=True)
    elif selected_status == "incomplete":
        prospective_users = prospective_users.filter(all_trainings_completed=False)
    if selected_user_type == "new":
        prospective_users = prospective_users.filter(nemo_user__isnull=True)
    elif selected_user_type == "nemo":
        prospective_users = prospective_users.filter(nemo_user__isnull=False)

    page = SortedPaginator(prospective_users, request, order_by="-last_updated").get_current_page()

    # if bool(request.GET.get("csv", False)):
    #     return export_prospective_users(request, prospective_users.order_by("-last_updated"))

    dictionary = {
        "page": page,
        "current_user_trainings": current_user_trainings,
        "user_is_staff": user_is_staff,
        "single_user_view": single_user_view,
        "selected_status": selected_status,
        "selected_user_type": selected_user_type,
        "available_trainings": OnlineTraining.objects.all(),
    }
    return render(request, "NEMO_online_training/user_trainings/user_trainings.html", dictionary)


@require_GET
@user_office_or_manager_required
def search_prospective_users(request):
    return render(request, "NEMO_online_training/user_trainings/user_search.html", {"form": ProspectiveUserForm()})


@user_office_or_manager_required
@require_GET
def prospective_users_search_results(request):
    nemo_users: HttpResponse = queryset_search_filter(
        User.objects.all(), ["first_name", "last_name", "username", "email"], request
    )
    prospective_users: HttpResponse = queryset_search_filter(
        ProspectiveUser.objects.all(), ["_first_name", "_last_name", "_email"], request
    )
    return HttpResponse(
        json.dumps(json.loads(prospective_users.content) + json.loads(nemo_users.content)), "application/json"
    )


@user_office_or_manager_required
@require_GET
def create_prospective_user_from_nemo_user(request, nemo_user_id):
    nemo_user = get_object_or_404(User, pk=nemo_user_id)
    prospective_user = ProspectiveUser.create_from_nemo_user(nemo_user)
    return redirect("online_user_trainings", prospective_user_id=prospective_user.id)


@user_office_or_manager_required
@require_POST
def create_prospective_user(request):
    form = ProspectiveUserForm(request.POST or None)
    if form.is_valid():
        prospective_user = form.save()
        return redirect("online_user_trainings", prospective_user_id=prospective_user.id)
    return render(request, "NEMO_online_training/user_trainings/user_search.html", {"form": form})


@login_required
@require_GET
def create_nemo_user_from_prospective_user(request, prospective_user_id):
    prospective_user = get_object_or_404(ProspectiveUser, pk=prospective_user_id)
    return redirect(
        reverse("create_or_modify_user", kwargs={"user_id": "new"})
        + f"?first_name={prospective_user.first_name}&last_name={prospective_user.last_name}&email={prospective_user.email}&correlation_id={prospective_user_id}"
    )


@login_required
@require_GET
def training_without_assignment(request, online_training_id):
    online_training = get_object_or_404(OnlineTraining, pk=online_training_id)
    if not online_training.allow_self_enrollment:
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {
                "title": "Error",
                "message": "This training is not available for self enrollment, contact staff to be assigned this training",
            },
        )
    if not online_training.enabled:
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {"title": "Error", "message": "This training is not available anymore"},
        )

    prospective_user = ProspectiveUser.create_from_nemo_user(request.user)
    online_user_training, created = OnlineUserTraining.objects.get_or_create(
        prospective_user=prospective_user, online_training=online_training, end=None
    )

    return redirect("online_training_user_training", user_training_id=online_user_training.id)


@require_GET
@login_required
def training(request, user_training_id):
    online_training_user = get_object_or_404(OnlineUserTraining, pk=user_training_id)
    if (
        not online_training_user.prospective_user.nemo_user
        or request.user != online_training_user.prospective_user.nemo_user
    ):
        return render(
            request,
            "NEMO_online_training/error_message.html",
            {"title": "Error", "message": "You do not have permission to complete this training"},
        )

    return redirect(online_training_user.generate_link())


@user_office_or_manager_required
@require_POST
def add_training_to_user(request, prospective_user_id, online_training_id):
    prospective_user = get_object_or_404(ProspectiveUser, pk=prospective_user_id)
    online_training = get_object_or_404(OnlineTraining, pk=online_training_id)

    form = OnlineUserTrainingForm(request.POST)
    form.instance.prospective_user = prospective_user
    form.instance.online_training = online_training

    if form.is_valid():
        online_training_user = form.save()
        online_training_user.generate_and_send_new_email()
        return JsonResponse({"success": True})
    else:
        # Return form errors in a format that JavaScript can handle
        errors = {}
        for field, error_list in form.errors.items():
            errors[field] = error_list
        return JsonResponse({"success": False, "errors": errors}, status=400)


@require_GET
@ensure_csrf_cookie
def public_user_training(request, signed_user_training_id):
    user_training_id = None

    try:
        signer = TimestampSigner()
        max_age = OnlineTrainingCustomization.get_int("online_training_link_validity_minutes") * 60

        # Just check validity
        user_training_id = signer.unsign(signed_user_training_id)
        online_training_user = get_object_or_404(OnlineUserTraining, id=user_training_id)
        if online_training_user.completed():
            return render(
                request,
                "NEMO_online_training/error_message.html",
                {"title": "Success", "message": _("This training has been completed!")},
            )

        # Now check the time limit
        user_training_id = signer.unsign(signed_user_training_id, max_age=max_age)

        # Extract the timestamp manually. Django token format is: value:timestamp:signature
        # We grab the middle part (timestamp) which is Base62 encoded.
        parts = signed_user_training_id.rsplit(":", 2)
        if len(parts) < 3:
            raise BadSignature()
    except (BadSignature, SignatureExpired) as e:
        if isinstance(e, SignatureExpired) and request.user and request.user.is_authenticated:
            return redirect("online_training_user", user_training_id=user_training_id)
        return render(
            request,
            "NEMO_online_training/public/invalid_training_link.html",
            {"user_training_id": user_training_id},
        )

    online_training_user.prospective_user.last_accessed = timezone.now()
    online_training_user.prospective_user.save(update_fields=["last_accessed"])
    error = check_training_validity(online_training_user)
    if error:
        return render(request, "NEMO_online_training/error_message.html", {"title": "Error", "message": error})
    else:
        completion_token = TimestampSigner().sign(user_training_id)
        online_training_user.start = timezone.now()
        online_training_user.save(update_fields=["start"])

        training_context = {
            "training_user": online_training_user.prospective_user,
            "training": online_training_user.online_training,
            "record": online_training_user,
        }

        online_training_rendered = render_email_template(
            online_training_user.online_training.html_content, training_context, request
        )
        return render(
            request,
            "NEMO_online_training/public/user_training.html",
            {
                "online_training_user": online_training_user,
                "online_training_rendered": online_training_rendered,
                "expires_at": online_training_user.start
                + timedelta(minutes=online_training_user.online_training.completion_time_limit),
                "completion_token": completion_token,
            },
        )


@require_POST
def public_generate_user_training_email(request, user_training_id):
    online_training_user = OnlineUserTraining.objects.filter(id=user_training_id).first()
    if not online_training_user:
        if request.POST.get("popup"):
            return HttpResponseBadRequest(_("Invalid link"))
        else:
            return render(
                request,
                "NEMO_online_training/error_message.html",
                {"title": "Error", "message": _("Invalid link")},
                status=400,
            )
    online_training_user.generate_and_send_new_email()
    return render(request, "NEMO_online_training/public/new_link_email_confirmation.html")


@require_POST
def public_complete_user_training(request):
    signed_user_training_id = request.POST.get("completion_token")
    user_training_id = None

    try:
        signer = TimestampSigner()
        # Just check validity
        user_training_id = signer.unsign(signed_user_training_id)
        # Now check the time limit
        online_training_user = get_object_or_404(OnlineUserTraining, pk=user_training_id)
        dynamic_limit_seconds = online_training_user.online_training.completion_time_limit * 60
        signer.unsign(signed_user_training_id, max_age=dynamic_limit_seconds)
    except (BadSignature, SignatureExpired):
        return render(
            request, "NEMO_online_training/public/invalid_training_link.html", {"user_training_id": user_training_id}
        )

    error = check_training_validity(online_training_user)
    if error:
        return render(request, "NEMO_online_training/error_message.html", {"title": "Error", "message": error})
    else:
        data = {}
        for key, values in request.POST.lists():
            # remove completion token and csrf token from the completion data
            if key in ["csrfmiddlewaretoken", "completion_token"]:
                continue
            if len(values) == 1:
                data[key] = values[0]
            else:
                data[key] = values
        online_training_user.complete(data)

    return HttpResponse()


def check_training_validity(online_user_training: OnlineUserTraining) -> Optional[Promise | str]:
    if not online_user_training.online_training.enabled:
        return _("This training is not available anymore!")
    if online_user_training.has_training_expired():
        return _(f"This training expired on {format_datetime(online_user_training.due_date)}")
    if online_user_training.end:
        return _("This training has been completed!")
    return None
