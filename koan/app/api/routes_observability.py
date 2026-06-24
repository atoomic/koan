"""REST API observability routes: usage, metrics, and log tails."""

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.api.auth import require_token

bp = Blueprint("observability", __name__)


def _instance_dir() -> Path:
    return current_app.config["INSTANCE_DIR"]


def _koan_root() -> Path:
    return current_app.config["KOAN_ROOT"]


@bp.route("/v1/usage")
@require_token
def usage():
    from app.usage_service import build_usage_payload

    try:
        days = int(request.args.get("days", "7"))
    except (ValueError, TypeError):
        days = 7
    try:
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        offset = 0
    stacked = request.args.get("stacked", "false").lower() in ("true", "1", "yes")
    return jsonify(build_usage_payload(
        _instance_dir(),
        days=days,
        project=request.args.get("project", ""),
        granularity=request.args.get("granularity", "day"),
        stacked=stacked,
        offset=offset,
    ))


@bp.route("/v1/metrics")
@require_token
def metrics():
    from app.mission_metrics import (
        compute_global_metrics,
        compute_project_metrics,
        compute_project_trend,
    )

    try:
        days = max(0, min(int(request.args.get("days", "30")), 365))
    except (ValueError, TypeError):
        days = 30
    project = request.args.get("project", "")
    instance = str(_instance_dir())

    if project:
        data = compute_project_metrics(instance, project, days=days)
        data["trend"] = compute_project_trend(instance, project, days=days)
        return jsonify(data)

    data = compute_global_metrics(instance, days=days)
    for proj in data["by_project"]:
        data["by_project"][proj]["trend"] = compute_project_trend(instance, proj, days=days)
    return jsonify(data)


@bp.route("/v1/logs")
@require_token
def logs():
    from app.log_reader import LOG_DEFAULT_LIMIT, read_logs

    source = request.args.get("source", "all")
    try:
        limit = int(request.args.get("limit", LOG_DEFAULT_LIMIT))
    except (ValueError, TypeError):
        limit = LOG_DEFAULT_LIMIT
    q = request.args.get("q", "")
    return jsonify(read_logs(_koan_root(), source=source, limit=limit, q=q))
