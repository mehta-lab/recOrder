from pathlib import Path
from iohub.convert import TIFFConverter
from iohub.ngff import open_ome_zarr
from recOrder.cli.utils import create_empty_hcs_zarr

import time, threading, os, shutil, json

def convertData(tif_path, latest_out_path, prefix="", data_type_str="ometiff"):
    converter = TIFFConverter(
        os.path.join(tif_path , prefix),
        latest_out_path,
        data_type=data_type_str,
        grid_layout=False,
    )
    converter.run()    

def runConvert(ome_tif_path):    
    out_path = os.path.join(Path(ome_tif_path).parent.absolute(), ("raw_" + Path(ome_tif_path).name + ".zarr"))
    convertData(ome_tif_path, out_path)

def runAcq(input_path="", onlyPrint=False, waitBetweenT=30):

    output_store_path = os.path.join(Path(input_path).parent.absolute(), ("output_" + Path(input_path).name))

    if Path(output_store_path).exists():
        shutil.rmtree(output_store_path)
        time.sleep(1)

    input_data = open_ome_zarr(input_path, mode="r")
    channel_names = input_data.channel_names

    position_keys: list[tuple[str]] = []

    for path, pos in input_data.positions():
        # print(path)
        # print(pos["0"].shape)
    
        shape = pos["0"].shape
        dtype = pos["0"].dtype
        chunks = pos["0"].chunks
        scale = (1, 1, 1, 1, 1)
        position_keys.append(path.split("/"))

    if onlyPrint:
        print("shape: ", shape)
        print("position_keys: ", position_keys)
        input_data.print_tree()
        return
        
    create_empty_hcs_zarr(
        output_store_path,
        position_keys,
        shape,
        chunks,
        scale,
        channel_names,
        dtype,
        {},
    )
    output_dataset = open_ome_zarr(output_store_path, mode="r+")

    if "Summary" in input_data.zattrs.keys():
        output_dataset.zattrs["Summary"] = input_data.zattrs["Summary"]

    output_dataset.zattrs.update({"FinalDimensions": {
            "channel": shape[1],
            "position": len(position_keys),
            "time": shape[0],
            "z": shape[2]
        }
    })
   
    for t in range(shape[0]):
        for p in range(len(position_keys)):
            for z in range(shape[2]):
                for c in range(shape[1]):
                    position_key_string = "/".join(position_keys[p])
                    img_src = input_data[position_key_string][0][t, c, z]

                    img_data = output_dataset[position_key_string][0]
                    img_data[t, c, z] = img_src

                    output_dataset.zattrs.update({"CurrentDimensions": {
                            "channel": c+1,
                            "position": p+1,
                            "time": t+1,
                            "z": z+1
                        }
                    })
        
        # output_dataset.print_tree()
        required_order = ['time', 'position', 'z', 'channel']
        my_dict = output_dataset.zattrs["CurrentDimensions"]
        sorted_dict_acq = {k: my_dict[k] for k in sorted(my_dict, key=lambda x: required_order.index(x))}
        print("Writer thread - Acquisition Dim:", sorted_dict_acq)
        time.sleep(waitBetweenT) # sleep after every t

    output_dataset.close

def runAcquire(input_path, onlyPrint, waitBetweenT):
    runThread1Acq = threading.Thread(target=runAcq, args=(input_path, onlyPrint, waitBetweenT))
    runThread1Acq.start()

def test(input_path, readerThread=True, onlyPrint=False, waitBetweenT=30):
    
    input_poll_data_path = os.path.join(Path(input_path).parent.absolute(), ("output_" + Path(input_path).name))

    runAcquire(input_path, onlyPrint, waitBetweenT)

    if not readerThread:
        return

    time.sleep(15)
    
    required_order = ['time', 'position', 'z', 'channel']
    while True:
        data = open_ome_zarr(input_poll_data_path, mode="r")
        print("="*60)
        if "CurrentDimensions" in data.zattrs.keys():
            my_dict = data.zattrs["CurrentDimensions"]
            sorted_dict_acq = {k: my_dict[k] for k in sorted(my_dict, key=lambda x: required_order.index(x))}
            print("Reader thread - Acquisition Dim:", sorted_dict_acq)
        
        if "FinalDimensions" in data.zattrs.keys():
            my_dict = data.zattrs["FinalDimensions"]
            sorted_dict_final = {k: my_dict[k] for k in sorted(my_dict, key=lambda x: required_order.index(x))}
            print("Reader thread - Final Dim:", sorted_dict_final)
            if json.dumps(sorted_dict_acq) == json.dumps(sorted_dict_final):
                print("Reader thread - Acquisition Finished !")
                break
        print("="*60)
        time.sleep(10)

# Step 1:
# Convert an existing ome-tif recOrder acquisition, preferably with all dims (t, p, z, c)
# This will convert an existing ome-tif to a .zarr storage
# ome_tif_path = "..\\ome-zarr_data\\recOrderAcq\\test\\snap_6D_ometiff_1"
# runConvert(ome_tif_path)

# Step 2:
# run the test to simulate Acquiring a recOrder .zarr store

# input_path = "..\\ome-zarr_data\\recOrderAcq\\test\\raw_snap_6D_ometiff_1.zarr"
# waitBetweenT = 30
# onlyPrint = False
# readerThread = False
# test(input_path, readerThread, onlyPrint, waitBetweenT)
