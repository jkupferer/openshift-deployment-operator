#!/usr/bin/env python

import kopf
import kubernetes
import os

if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/namespace'):
    kubernetes.config.load_incluster_config()
    namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()
else:
    kubernetes.config.load_kube_config()
    namespace = kubernetes.config.list_kube_config_contexts()[1]['context']['namespace']

deployment_namespaces = [namespace]
if os.environ.get('DEPLOYMENT_NAMESPACES'):
    deployment_namespaces.extend(os.environ['DEPLOYMENT_NAMESPACES'].split(','))

core_v1_api = kubernetes.client.CoreV1Api()
custom_objects_api = kubernetes.client.CustomObjectsApi()

def manage_deployment_for_imagestream(deployment, imagestream, imagestream_label, tag_name, logger):
    docker_image_reference = None

    image_reference = None
    image_reference_prefix = None
    for tag in imagestream.get('status', {}).get('tags', []):
        if tag['tag'] == tag_name:
            image_reference = tag['items'][0]['dockerImageReference']
            image_reference_prefix = image_reference[0:image_reference.index('@sha256:')+8]

    if not image_reference:
        logger.warning(
            'Unable to resolve image reference for %s %s in namespace %s',
            deployment['kind'], deployment['metadata']['name'], deployment['metadata']['namespace']
        )
        return

    changed = False
    matched = False
    for container in deployment['spec']['template']['spec']['containers']:
        container_image = container['image']
        if container_image == imagestream_label \
        or container_image.startswith(image_reference_prefix):
            matched = True
            if container_image != image_reference:
                container['image'] = image_reference
                changed = True

    if changed:
        custom_objects_api.replace_namespaced_custom_object(
            'apps', 'v1', deployment['metadata']['namespace'], 'deployments',
            deployment['metadata']['name'], deployment
        )
        logger.info(
            'Updated %s %s in namespace %s',
            deployment['kind'], deployment['metadata']['name'], deployment['metadata']['namespace']
        )
    elif not matched:
        logger.warning(
            'Imagestream did not match any containers for %s %s in namespace %s',
            deployment['kind'], deployment['metadata']['name'], deployment['metadata']['namespace']
        )
        return

def manage_deployments_for_imagestream(imagestream, logger):
    imagestream_label = 'imagestreams.image.openshift.io/{0}'.format(imagestream['metadata']['name'])
    for deployment in custom_objects_api.list_namespaced_custom_object(
        'apps', 'v1', namespace, 'deployments',
        label_selector=imagestream_label
    ).get('items', []):
        tag_name = deployment['metadata']['labels'][imagestream_label]
        manage_deployment_for_imagestream(deployment, imagestream, imagestream_label, tag_name, logger)

    imagestream_label = 'imagestreams.image.openshift.io/{0}.{1}'.format(namespace, imagestream['metadata']['name'])
    for deployment_namespace in deployment_namespaces:
        for deployment in custom_objects_api.list_namespaced_custom_object(
            'apps', 'v1', deployment_namespace, 'deployments',
            label_selector=imagestream_label
        ).get('items', []):
            tag_name = deployment['metadata']['labels'][imagestream_label]
            manage_deployment_for_imagestream(deployment, imagestream, imagestream_label, tag_name, logger)

@kopf.on.event('image.openshift.io', 'v1', 'imagestreams')
def watch_imagestreams(event, logger, **_):
    '''
    Watch imagestreams and update deployments that reference this imagestream.
    '''
    if event['type'] in ['ADDED', 'MODIFIED', None]:
        imagestream = event['object']
        manage_deployments_for_imagestream(imagestream, logger)
    elif event['type'] == 'DELETED':
        # Nothing to do on delete.
        pass
    else:
        logger.warning('Unhandled ResourceClaim event %s', event)
