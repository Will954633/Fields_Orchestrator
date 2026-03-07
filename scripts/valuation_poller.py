#!/usr/bin/env python3
"""
Valuation Request Poller

Polls system_monitor.valuation_requests every 30 seconds for pending
on-demand valuation requests and dispatches them to on_demand_valuation.py.

Run as a service: fields-valuation-poller
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

from pymongo import MongoClient

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds
SCRIPT_PATH = Path(__file__).parent / 'on_demand_valuation.py'
VENV_PYTHON = '/home/fields/venv/bin/python3'


def get_client():
    uri = os.environ.get('COSMOS_CONNECTION_STRING')
    if not uri:
        logger.error('COSMOS_CONNECTION_STRING not set')
        sys.exit(1)
    return MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)


def process_one(req):
    """Process a single valuation request by calling on_demand_valuation.py."""
    suburb = req.get('suburb')
    property_id = req.get('property_id')
    req_id = req['_id']

    logger.info(f'Processing request {req_id}: suburb={suburb}, id={property_id}')

    # Mark as processing
    client = get_client()
    queue = client['system_monitor']['valuation_requests']
    queue.update_one(
        {'_id': req_id},
        {'$set': {'status': 'processing', 'started_at': datetime.utcnow()}}
    )
    client.close()

    # Run the valuation script as a subprocess
    env = {**os.environ}
    cmd = [
        VENV_PYTHON, str(SCRIPT_PATH),
        '--suburb', suburb,
        '--property-id', property_id,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=env,
            cwd=str(Path(__file__).parent.parent),
        )

        client = get_client()
        queue = client['system_monitor']['valuation_requests']

        if result.returncode == 0:
            queue.update_one(
                {'_id': req_id},
                {'$set': {
                    'status': 'completed',
                    'completed_at': datetime.utcnow(),
                }}
            )
            logger.info(f'Request {req_id} completed successfully')
        else:
            error_msg = (result.stderr or result.stdout or 'Unknown error')[-500:]
            queue.update_one(
                {'_id': req_id},
                {'$set': {
                    'status': 'failed',
                    'completed_at': datetime.utcnow(),
                    'error': error_msg,
                }}
            )
            logger.error(f'Request {req_id} failed: {error_msg}')

        client.close()

    except subprocess.TimeoutExpired:
        logger.error(f'Request {req_id} timed out after 600s')
        client = get_client()
        client['system_monitor']['valuation_requests'].update_one(
            {'_id': req_id},
            {'$set': {
                'status': 'failed',
                'completed_at': datetime.utcnow(),
                'error': 'Valuation timed out after 600 seconds',
            }}
        )
        client.close()

    except Exception as e:
        logger.error(f'Request {req_id} exception: {e}')
        try:
            client = get_client()
            client['system_monitor']['valuation_requests'].update_one(
                {'_id': req_id},
                {'$set': {
                    'status': 'failed',
                    'completed_at': datetime.utcnow(),
                    'error': str(e),
                }}
            )
            client.close()
        except Exception:
            pass


def poll_loop():
    """Main polling loop."""
    logger.info('Valuation poller started')
    logger.info(f'Polling every {POLL_INTERVAL}s for pending requests')

    while True:
        try:
            client = get_client()
            queue = client['system_monitor']['valuation_requests']

            # Find oldest pending request
            req = queue.find_one(
                {'status': 'pending'},
                sort=[('requested_at', 1)]
            )
            client.close()

            if req:
                process_one(req)
            else:
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info('Poller stopped by user')
            break
        except Exception as e:
            logger.error(f'Poll loop error: {e}')
            time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    poll_loop()
