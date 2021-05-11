from waveorder.io.reader import MicromanagerReader
import os
from recOrder.pipelines.pipeline_constructor import PipelineConstructor
from recOrder.io.config_reader import ConfigReader

def run_pipeline(config: ConfigReader):

    for sample in config.samples:
        print(os.path.join(config.data_dir, sample))
        data = MicromanagerReader(os.path.join(config.data_dir, sample), config.data_type)
        pipeline = PipelineConstructor(config, data, sample)
        pipeline.run()