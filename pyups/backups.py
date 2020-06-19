import boto3
import logging
import pyups.arrays as arrays
from pathlib import Path
from pyups.configuration import get_configuration
from pyups.state.repository import StateRepository
from botocore.exceptions import ClientError

def backup(repository_path: Path) -> None:
    """
    Parameters
    ----------
    path
        The file system path to the directory that will be backed up. This path 
        is expected to be an existing directory.
    """
    s3 = boto3.resource('s3')
    configuration = get_configuration(repository_path)
    bucket = s3.Bucket(configuration.s3_bucket)
    states = StateRepository(root_path=repository_path)

    any_changes = False
    to_delete = []
    for c in states.changes():
        any_changes = True
        if (c.item_path.exists()):
            if (not c.previous_state) or c.previous_state.hash != c.new_state.hash:
                logging.info(f'Uploading item {c.item.as_posix()}.')
                bucket.upload_file(c.item_path.as_posix(), f"content/{c.item.as_posix()}")
            else:
                logging.info(f'Content of item {c.item.as_posix()} has not changed, skipping upload.')
            c.commit()
        else:
            if c.new_state == None and c.previous_state != None:
                logging.info(f'Item {c.item.as_posix()} is no longer in filesystem. It will be deleted.')
                to_delete.append(c)

    for sublist in arrays.partition(array=to_delete, max_length=500):
        keys = [ { 'Key': f"content/{c.item.as_posix()}" } for c in sublist ]
        response = bucket.delete_objects(Delete={ 'Objects': keys , 'Quiet': True})

        failed = []
        if 'Errors' in response:
            # List of objects or items that failed to be deleted. Documentation says
            # the list should contain only the things that encountered an error while
            # deleting.
            failed = [ o['Key'] for o in response['Errors'] ]

        for c in to_delete:
            if any(m for m in failed if m == c.item.as_posix()):
                # This means we could not delete the item.
                logging.warn(f'Could not delete {c.item.as_posix()}')
            else:
                c.commit()

    if any_changes == False:
        logging.info("No changes were detected")