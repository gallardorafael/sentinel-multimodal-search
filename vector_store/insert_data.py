import argparse
import logging
import pprint
from typing import Any

from PIL import Image
from pymilvus import MilvusClient
from rich.progress import track

from datasets import Flickr30kDataset, FlickrDataset
from feature_extraction import JinaCLIPFeatureExtractor, MultimodalFeatureExtractor

from .defaults import *

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def parse_args():
    """Parses the arguments from the command line."""
    parser = argparse.ArgumentParser(description="Insert data into Milvus")
    parser.add_argument(
        "--data_path", type=str, help="Path to the root folder of the data", required=True
    )
    parser.add_argument(
        "--data_type",
        type=str,
        help="Dataset type to be inserted",
        choices=["flickr8k", "flickr30k"],
    )
    parser.add_argument("--uri", type=str, default=MILVUS_URI, help="Host of Milvus server")
    parser.add_argument(
        "--collection_name", type=str, default=MILVUS_COLLECTION_NAME, help="Collection name"
    )
    parser.add_argument("--db_name", type=str, default=MILVUS_DB_NAME, help="Database name")
    parser.add_argument(
        "--dimension", type=int, default=VECTOR_FIELD_DIM, help="Dimension of the vectors"
    )
    parser.add_argument("--metric_type", type=str, default=DEFAULT_METRIC, help="Metric type")
    parser.add_argument(
        "--delete_existing_collection", action="store_true", help="Delete existing collection"
    )

    return parser.parse_args()


def create_collection(
    client: MilvusClient,
    collection_name: str,
    vector_field_name: str,
    dimension: int,
    metric_type: str,
    delete_existing_collection: bool = False,
) -> None:
    """Creates a collection in Milvus.

    Args:
        client: MilvusClient object.
        collection_name (str): Name of the collection.
        vector_field_name (str): Name of the vector field.
        dimension (int): Dimension of the embeddings.
        metric_type (str): Metric type.
        delete_existing_collection (bool): Whether to delete the existing collection with the same name.
    """
    if collection_name in client.list_collections():
        if not delete_existing_collection:
            logger.warning(
                "Inserting data into an existing collection %s, run the script with the flag --delete_existing_collection for a fresh collection with the same name (destroying the existing one)."
                % collection_name
            )
            return
        else:
            client.drop_collection(collection_name=collection_name)
            logger.info("Collection %s dropped." % collection_name)

    client.create_collection(
        collection_name=collection_name,
        vector_field_name=vector_field_name,
        dimension=dimension,
        auto_id=True,
        enable_dynamic_field=True,
        metric_type=metric_type,
    )


def insert_data(
    dataset: Any,
    client: MilvusClient,
    collection_name: str,
    vector_field_name: str,
    feature_extractor: MultimodalFeatureExtractor,
) -> None:
    inserted_count = 0
    for image_object in track(dataset, description=f"Inserting {len(dataset)} images into Milvus"):
        # read image
        image = Image.open(image_object.image_path)

        # extract embeddings
        embeddings = feature_extractor.get_image_features(image)

        # insert into collection
        caption = image_object.best_caption

        res = client.insert(
            collection_name=collection_name,
            data=[
                {
                    "filename": image_object.image_path,
                    "caption": caption,
                    vector_field_name: embeddings,
                }
            ],
        )
        if res["insert_count"] > 0:
            inserted_count += res["insert_count"]
    logger.info("Inserted %d images into Milvus" % inserted_count)


def main():
    """Main function to run the insert operation of all the data into Milvus."""
    args = parse_args()
    logger.info("Running insert operation with arguments: %s" % pprint.pp(args))

    # initialize the vector db client
    client = MilvusClient(uri=args.uri, db_name=args.db_name)

    # initialize the feature extractor
    extractor = JinaCLIPFeatureExtractor()

    # creating collection
    create_collection(
        client=client,
        collection_name=args.collection_name,
        vector_field_name=DEFAULT_VECTOR_FIELD_NAME,
        dimension=args.dimension,
        metric_type=args.metric_type,
        delete_existing_collection=args.delete_existing_collection,
    )

    # inserting data from the Flickr dataset
    if args.data_type == "flickr8k":
        dataset = FlickrDataset(root_path=args.data_path)
        insert_data(
            dataset,
            client=client,
            collection_name=args.collection_name,
            vector_field_name=DEFAULT_VECTOR_FIELD_NAME,
            feature_extractor=extractor,
        )
    elif args.data_type == "flickr30k":
        dataset = Flickr30kDataset(root_path=args.data_path)
        insert_data(
            dataset,
            client=client,
            collection_name=args.collection_name,
            vector_field_name=DEFAULT_VECTOR_FIELD_NAME,
            feature_extractor=extractor,
        )
    else:
        raise ValueError("Invalid dataset type")


if __name__ == "__main__":
    main()
