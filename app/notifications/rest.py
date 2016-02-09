import json

import boto3
from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)
from itsdangerous import URLSafeSerializer
from app import notify_alpha_client
from app import api_user
from app.dao import (templates_dao, services_dao)
import re
from app import celery

mobile_regex = re.compile("^\\+44[\\d]{10}$")

notifications = Blueprint('notifications', __name__)


@notifications.route('/<notification_id>', methods=['GET'])
def get_notifications(notification_id):
    return jsonify(notify_alpha_client.fetch_notification_by_id(notification_id)), 200


@celery.task(name="make-sms", bind="True")
def send_sms(self, to, template):
    print('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    from time import sleep
    sleep(0.5)
    print('finished')
    #notify_alpha_client.send_sms(mobile_number=to, message=template)


@notifications.route('/sms', methods=['POST'])
def create_sms_notification():
    notification = request.get_json()['notification']
    errors = {}
    to, to_errors = validate_to(notification)
    if to_errors['to']:
        errors.update(to_errors)

    # TODO: should create a different endpoint for the admin client to send verify codes.
    if api_user['client'] == current_app.config.get('ADMIN_CLIENT_USER_NAME'):
        content, content_errors = validate_content_for_admin_client(notification)
        if content_errors['content']:
            errors.update(content_errors)
        if errors:
            return jsonify(result="error", message=errors), 400

        return jsonify(notify_alpha_client.send_sms(mobile_number=to, message=content)), 200

    else:
        to, restricted_errors = validate_to_for_service(to, api_user['client'])
        if restricted_errors['restricted']:
            errors.update(restricted_errors)

        template, template_errors = validate_template(notification, api_user['client'])
        if template_errors['template']:
            errors.update(template_errors)
        if errors:
            return jsonify(result="error", message=errors), 400

        # add notification to the queue
        service = services_dao.get_model_services(api_user['client'], _raise=False)
        #_add_notification_to_queue(template.id, service, 'sms', to)
        send_sms.apply_async((to, template.content), queue=str(service.id))
        return jsonify(success=True)  # notify_alpha_client.send_sms(mobile_number=to, message=template.content)), 200


@notifications.route('/email', methods=['POST'])
def create_email_notification():
    notification = request.get_json()['notification']
    errors = {}
    for k in ['to', 'from', 'subject', 'message']:
        k_error = validate_required_and_something(notification, k)
        if k_error:
            errors.update(k_error)

    if errors:
        return jsonify(result="error", message=errors), 400

    return jsonify(notify_alpha_client.send_email(
        notification['to'],
        notification['message'],
        notification['from'],
        notification['subject']))


def validate_to_for_service(mob, service_id):
    errors = {"restricted": []}
    service = services_dao.get_model_services(service_id=service_id)
    if service.restricted:
        valid = False
        for usr in service.users:
            if mob == usr.mobile_number:
                valid = True
                break
        if not valid:
            errors['restricted'].append('Invalid phone number for restricted service')
    return mob, errors


def validate_to(json_body):
    errors = {"to": []}
    mob = json_body.get('to', None)
    if not mob:
        errors['to'].append('Required data missing')
    else:
        if not mobile_regex.match(mob):
            errors['to'].append('invalid phone number, must be of format +441234123123')
    return mob, errors


def validate_template(json_body, service_id):
    errors = {"template": []}
    template_id = json_body.get('template', None)
    template = ''
    if not template_id:
        errors['template'].append('Required data missing')
    else:
        try:
            template = templates_dao.get_model_templates(
                template_id=json_body['template'],
                service_id=service_id)
        except:
            errors['template'].append("Unable to load template.")
    return template, errors


def validate_content_for_admin_client(json_body):
    errors = {"content": []}
    content = json_body.get('template', None)
    if not content:
        errors['content'].append('Required content')

    return content, errors


def validate_required_and_something(json_body, field):
    errors = []
    if field not in json_body and json_body[field]:
        errors.append('Required data for field.')
    return {field: errors} if errors else None


def _add_notification_to_queue(template_id, service, msg_type, to):
    q = boto3.resource('sqs', region_name=current_app.config['AWS_REGION']).create_queue(
        QueueName=str(service.id))
    import uuid
    message_id = str(uuid.uuid4())
    notification = json.dumps({'message_id': message_id,
                               'service_id': str(service.id),
                               'to': to,
                               'message_type': msg_type,
                               'template_id': template_id})
    serializer = URLSafeSerializer(current_app.config.get('SECRET_KEY'))
    encrypted = serializer.dumps(notification, current_app.config.get('DANGEROUS_SALT'))
    q.send_message(MessageBody=encrypted,
                   MessageAttributes={'type': {'StringValue': msg_type, 'DataType': 'String'},
                                      'message_id': {'StringValue': message_id, 'DataType': 'String'},
                                      'service_id': {'StringValue': str(service.id), 'DataType': 'String'},
                                      'template_id': {'StringValue': str(template_id), 'DataType': 'String'}})

