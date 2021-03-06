import json
import logging
import os
import sys
import traceback
import torch.multiprocessing as mp

from random import shuffle

from agents.tmp_agent import TmpBlockAgent
from dataset_agreement_blocks.action_space import ActionSpace
from dataset_agreement_blocks.metadata_util import MetaDataUtil
from dataset_agreement_blocks.dataset_parser import DatasetParser
from learning.asynchronous.tmp_blocks_asynchronous_contextual_bandit_learning import TmpAsynchronousContextualBandit
from learning.asynchronous.tmp_blocks_supervised_learning import TmpSupervisedLearning
from models.incremental_model.incremental_model_emnlp import IncrementalModelEmnlp
from models.incremental_model.tmp_blocks_incremental_model_chaplot import TmpBlocksIncrementalModelChaplot
from server_blocks.blocks_server import BlocksServer
from setup_agreement_blocks.validate_setup_blocks import \
    BlocksSetupValidator
from utils.check_port import find_k_ports
from utils.launch_unity import launch_k_unity_builds
from utils.multiprocess_logger import MultiprocessingLoggerManager


def main():

    experiment_name = "blocks_save_image-test"
    experiment = "./results/" + experiment_name
    print("EXPERIMENT NAME: ", experiment_name)

    # Create the experiment folder
    if not os.path.exists(experiment):
        os.makedirs(experiment)

    # Define log settings
    log_path = experiment + '/train_baseline.log'
    multiprocess_logging_manager = MultiprocessingLoggerManager(
        file_path=log_path, logging_level=logging.INFO)
    master_logger = multiprocess_logging_manager.get_logger("Master")
    master_logger.log("----------------------------------------------------------------")
    master_logger.log("                    STARING NEW EXPERIMENT                      ")
    master_logger.log("----------------------------------------------------------------")

    with open("data/blocks/config.json") as f:
        config = json.load(f)
    with open("data/shared/contextual_bandit_constants.json") as f:
        constants = json.load(f)
    print(json.dumps(config,indent=2))
    setup_validator = BlocksSetupValidator()
    setup_validator.validate(config, constants)

    # log core experiment details
    master_logger.log("CONFIG DETAILS")
    for k, v in sorted(config.items()):
        master_logger.log("    %s --- %r" % (k, v))
    master_logger.log("CONSTANTS DETAILS")
    for k, v in sorted(constants.items()):
        master_logger.log("    %s --- %r" % (k, v))
    master_logger.log("START SCRIPT CONTENTS")
    with open(__file__) as f:
        for line in f.readlines():
            master_logger.log(">>> " + line.strip())
    master_logger.log("END SCRIPT CONTENTS")

    action_space = ActionSpace(config)
    meta_data_util = MetaDataUtil()

    # Create vocabulary
    vocab = dict()
    vocab_list = open("./Assets/vocab_both").readlines()
    for i, tk in enumerate(vocab_list):
        token = tk.strip().lower()
        vocab[token] = i
    vocab["$UNK$"] = len(vocab_list)
    config["vocab_size"] = len(vocab_list) + 1

    # Number of processes
    num_processes = 6

    try:
        # create tensorboard
        tensorboard = None  # Tensorboard(experiment_name)

        # Create the model
        master_logger.log("CREATING MODEL")
        model_type = IncrementalModelEmnlp
        shared_model = model_type(config, constants)

        # make the shared model use share memory
        shared_model.share_memory()

        master_logger.log("MODEL CREATED")
        print("Created Model...")

        # Read the dataset
        all_train_data = DatasetParser.parse("testset.json", config)
        tune_split = []  # all_train_data[:num_tune]
        train_split = list(all_train_data[:])

        master_logger.log("Created train dataset of size %d " % len(train_split))
        master_logger.log("Created tuning dataset of size %d " % len(tune_split))

        # Start the training thread(s)
        ports = find_k_ports(num_processes)
        tmp_config = {k: v for k, v in config.items()}
        tmp_config["port"] = ports[0]

        server = BlocksServer(tmp_config, action_space)
        launch_k_unity_builds([ports[0]], "./simulators/blocks/retro_linux_build.x86_64")
        server.initialize_server()

        # Create a local model for rollouts
        local_model = model_type(config, constants)

        # Create the Agent
        tmp_agent = TmpBlockAgent(server=server,
                                  model=local_model,
                                  test_policy=None,
                                  action_space=action_space,
                                  meta_data_util=meta_data_util,
                                  config=config,
                                  constants=constants)
        tmp_agent.save_numpy_image(all_train_data, vocab, "test")

    except Exception:
        exc_info = sys.exc_info()
        traceback.print_exception(*exc_info)
        # raise e

if __name__ == "__main__":
    print("SETTING THE START METHOD ")
    main()
