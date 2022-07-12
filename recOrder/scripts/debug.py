from recOrder.io.zarr_converter import ZarrConverter
from waveorder.io import WaveorderReader

data_path = r'E:\2022_07_08 zebrafish imaging\fish2_withGFP_2'
output = r'E:\2022_07_08 zebrafish imaging\fish2_withGFP_2.zarr'

# ds = WaveorderReader(data_path)

converter = ZarrConverter(data_path, output)
converter.run_conversion()