import abc
import boto3
from botocore.exceptions import ClientError
from typing import Any, Dict, Type, List
from ..log import get_logger

logger = get_logger(__name__)


class _Singleton(type):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__instance = None  # Keep a strong reference

    def __call__(self, *args, **kwargs) -> Any:
        if self.__instance is not None:
            return self.__instance
        else:
            obj = super().__call__(*args, **kwargs)
            self.__instance = obj
            return obj


# TODO(p1): Make this thread safe
class _UIDSingleton(type):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__cache: Dict[str, Any] = {}  # Keep a strong reference

    def __call__(self, uid: str) -> Any:
        if uid in self.__cache:
            return self.__cache[uid]
        else:
            obj = super().__call__(uid)
            self.__cache[uid] = obj
            return obj


class _UIDSingletonABC(_UIDSingleton, abc.ABCMeta):
    pass


class S3CheckpointHelper():
    s3_client: Any = None

    @classmethod
    def get_client(cls: Type):
        if not cls.s3_client:
            cls.s3_client = boto3.client('s3')
        return cls.s3_client

    @classmethod
    def ping(cls: Type, bucket_name: str) -> bool:
        try:
            cls.get_client().head_bucket(Bucket=bucket_name)
            return True
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                logger.debug("Bucket does not exist.")
            elif error_code == 403:
                logger.debug("Bucket exists but access is denied.")
            else:
                logger.debug(f"Unexpected error: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error: {e}")
            return False

    @classmethod
    def exists(cls: Type, bucket_name: str, job_id: str, uid: str, ckpt_name: str) -> bool:
        object_key = f'{job_id}/{uid}/{ckpt_name}'
        try:
            cls.get_client().head_object(Bucket=bucket_name, Key=object_key)
            return True
        except ClientError as e:
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                logger.debug("Object does not exist.")
            else:
                logger.debug(f"Unexpected error: {e}")
            return False
        except Exception as e:
            logger.debug(f"Unexpected error: {e}")
            return False

    @classmethod
    def list(cls: Type, bucket_name: str, job_id: str) -> Dict[str, Any]:
        all_checkpoints: Dict[str, List] = {}
        path = f'{job_id}/'

        response = cls.get_client().list_objects_v2(Bucket=bucket_name, Prefix=path, Delimiter='/')

        if response.get('CommonPrefixes'):
            for obj in response.get('CommonPrefixes'):
                folder_path = obj.get('Prefix')
                folder_name = folder_path.strip('/').split('/')[-1]
                next_response = cls.get_client().list_objects_v2(Bucket=bucket_name,
                                                                 Prefix=folder_path,
                                                                 Delimiter='/')
                if next_response.get('Contents'):
                    all_checkpoints[folder_name] = []
                    for next_obj in next_response.get('Contents'):
                        file_path = next_obj.get('Key')
                        file_name = file_path.strip('/').split('/')[-1]
                        all_checkpoints[folder_name].append(file_name)

        return all_checkpoints

    @classmethod
    def save(cls: Type, bucket_name: str, job_id: str, uid: str, ckpt_name: str, checkpoint_data: bytes) -> None:
        object_key = f'{job_id}/{uid}/{ckpt_name}'
        cls.get_client().put_object(Bucket=bucket_name, Key=object_key, Body=checkpoint_data)

    @classmethod
    def load(cls: Type, bucket_name: str, job_id: str, uid: str, ckpt_name: str) -> bytes:
        object_key = f'{job_id}/{uid}/{ckpt_name}'
        response = cls.get_client().get_object(Bucket=bucket_name, Key=object_key)
        checkpoint_data_from_s3 = response['Body'].read()

        return checkpoint_data_from_s3

    @classmethod
    def delete(cls: Type, bucket_name: str, job_id: str, uid: str, ckpt_name: str) -> None:
        object_key = f'{job_id}/{uid}/{ckpt_name}'
        cls.get_client().delete_object(Bucket=bucket_name, Key=object_key)
