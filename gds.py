import copy
from dataclasses import dataclass
from math import ceil, floor
from phidl import Device, set_quickplot_options
from phidl import quickplot
import phidl.geometry as pg
import phidl.routing as pr
import numpy as np
from collections.abc import Callable

set_quickplot_options(blocking=True, show_subports=True)

#vanadium-1
#gold-2
#removed GaAs - 3
#crystal blank - 8

#sweep within waveguide defect width from 0.515-0.63
#sweep across x electrode gap from 0.1 to max, 0.5 (geometrically limited)

@dataclass
class DeviceParameters:
    total_length: float

    crystal_length: float
    crystal_width: float
    bridge_width: float
    defect_length: float
    defect_width: float

    lattice_constant: float
    crystal_count: int
    outline_width: float
    
    electrode_overlap: float
    external_electrode_width: float
    external_electrode_skew: float

    crystal_layer: int = 8
    outline_layer: int = 3
    electrode_layer: int = 1
    
    shorted: bool = False
    unetched: bool = False
    off_defect: bool = False

    def half_crystal_length(self) -> float:
        return self.lattice_constant*self.crystal_count
    
    def total_crystal_length(self) -> float:
        return self.half_crystal_length()*2 + self.defect_length
        

def generate_device(parameters: DeviceParameters):
    assert parameters.crystal_count % 2 == 1

    device = Device()

    half_crystal = Device()

    crystal_t = pg.rectangle((parameters.crystal_length, parameters.crystal_width), parameters.crystal_layer)

    half_crystal.add_ref([crystal_t] * parameters.crystal_count)

    half_crystal.distribute(spacing=parameters.lattice_constant, separation=False, edge="x")
    half_crystal.align(alignment='y')
    half_crystal.move(half_crystal.center, destination=(0, 0))
    
    bridge=half_crystal.add_ref(pg.straight((parameters.bridge_width, parameters.half_crystal_length()), layer=parameters.crystal_layer))
    bridge.move(bridge.center, (0, 0))
    bridge.rotate(90)

    half_crystal.add_port(1, port=bridge.ports[1])
    half_crystal.add_port(2, port=bridge.ports[2])
    
    left_half = device.add_ref(half_crystal)
    right_half = device.add_ref(half_crystal)
    
    defect = device.add_ref(pg.straight((parameters.defect_width, parameters.defect_length), parameters.crystal_layer))
    defect.move(defect.center, (0,0))
    defect.rotate(90)
    
    left_half.connect(1, defect.ports[2])
    right_half.connect(2, defect.ports[1])

    device.add_port(2, port=left_half.ports[2])
    device.add_port(1, port=right_half.ports[1])
 
    internal_electrode = pg.rectangle((parameters.total_crystal_length(), max(parameters.defect_width, parameters.crystal_width)+0.1), layer=parameters.electrode_layer)
    internal_electrode.move(internal_electrode.center, defect.center)
    electrode_gap=pg.rectangle((parameters.defect_length-(parameters.electrode_overlap*2 if not parameters.off_defect else 0), parameters.total_crystal_length()))
    electrode_gap.move(electrode_gap.center, defect.center)
    # electrode_gap.rotate(-45, center=electrode_gap.center)

    if not parameters.shorted: internal_electrode=pg.boolean(internal_electrode, electrode_gap, operation="A-B", layer=parameters.electrode_layer)

    outline = pg.outline(device, parameters.outline_width, layer=parameters.outline_layer)

    for i in [1,2]:
        end_uncover = device.add_ref(pg.straight((parameters.total_crystal_length(), parameters.outline_width)))
        end_uncover.connect(1, device.ports[i])
        
        outline = pg.boolean(outline, end_uncover, operation='NOT', layer=parameters.outline_layer)
        device.remove(end_uncover)

    device.add_ref(internal_electrode)
    # device.add_ref(electrode_circles)
    if not parameters.unetched: device.add_ref(outline)

    external_electrode_length = (parameters.total_length - parameters.total_crystal_length())/2
    
    connector = pg.connector(width=parameters.external_electrode_width)
    
    for i in [1, 2]:
      external_connector_i = device.add_ref(connector)
      external_connector_i.move(external_connector_i.origin, device.ports[i].center + (external_electrode_length * (1 if i == 2 else -1), -parameters.external_electrode_skew))
      
      external_electrode = device.add_ref(pr.route_quad(device.ports[i], external_connector_i.ports[i%2+1], parameters.external_electrode_width, layer=parameters.electrode_layer))
      
      device.add_port("W" if i==1 else "E", port=external_connector_i.ports[i%2+1])
    
    return device

def generate_pads(
    layer: int
):
    pads = Device()

    pad = pg.straight((150, 150), layer=layer)

    left_pad = pads.add_ref(pad)
    center_pad = pads.add_ref(pad)
    right_pad = pads.add_ref(pad)

    pads.distribute(spacing=75)

    left_pad_top = pads.add_ref(pg.compass_multi((150, 150), ports={'E': 2, 'S': 1}, layer=layer))
    left_pad_top.connect('S1', left_pad.ports[1])

    right_pad_top = pads.add_ref(pg.compass_multi((150, 150), ports={'W': 2, 'S': 1}, layer=layer))
    right_pad_top.connect('S1', right_pad.ports[1])

    top_connection = pads.add_ref(pr.route_quad(right_pad_top.ports['W2'], left_pad_top.ports['E2'], layer=layer))

    pads.add_port("L", port=left_pad.ports[2])
    pads.add_port("C", port=center_pad.ports[2])
    pads.add_port("R", port=right_pad.ports[2])

    return pads
    
def generate_waveguides(
    device_count: int,
    device_spacing: float,
    gap_spacing: float,
    device_parameters: DeviceParameters,
    layer: int, 
    device_parameters_factory: Callable[[DeviceParameters, int], DeviceParameters],
    coordinates: str
):
    waveguides = Device()
    electrode_height = ceil(device_count/2)*device_spacing

    half_device_count = floor(device_count/2)

    center_electrode = waveguides.add_ref(pg.compass_multi((gap_spacing*2, electrode_height), {"N": 1, "E": half_device_count, "W": half_device_count}, layer=layer))

    for i in range(ceil(device_count/2)):
        device_i = waveguides.add_ref(generate_device(device_parameters_factory(device_parameters, i)))
        device_i.connect("E", center_electrode.ports[f"W{half_device_count-i}"], overlap=(device_parameters.total_length-gap_spacing)/2)

    for i in range(floor(device_count/2)):
        device_i = waveguides.add_ref(generate_device(device_parameters_factory(device_parameters, i+ceil(device_count/2))))
        device_i.connect("W", center_electrode.ports[f"E{half_device_count-i}"], overlap=(device_parameters.total_length-gap_spacing)/2)


    side_electrode_width = (600-gap_spacing*4)/2

    side_electrode = pg.compass_multi((side_electrode_width, electrode_height), {"N": 1, "S": 1, "E": device_count, "W": device_count}, layer=layer)
    left_electrode = waveguides.add_ref(side_electrode)
    left_electrode.connect(f"E1", center_electrode.ports["W1"], -gap_spacing)

    right_electrode = waveguides.add_ref(side_electrode)
    right_electrode.connect(f"W1", center_electrode.ports["E1"], -gap_spacing)

    left_electrode_bottom = waveguides.add_ref(pg.compass_multi((side_electrode_width, gap_spacing*2), ports={'E': 2, 'N': 1}, layer=layer))
    left_electrode_bottom.connect('N1', left_electrode.ports["S1"])

    right_electrode_bottom = waveguides.add_ref(pg.compass_multi((side_electrode_width, gap_spacing*2), ports={'W': 2, 'N': 1}, layer=layer))
    right_electrode_bottom.connect('N1', right_electrode.ports["S1"])

    bottom_connection = waveguides.add_ref(pr.route_quad(left_electrode_bottom.ports['E1'], right_electrode_bottom.ports['W1'], layer=layer))

    pads = waveguides.add_ref(generate_pads(layer=layer))

    pads.connect('C', center_electrode.ports["N1"], -100)

    waveguides.add_ref(pr.route_quad(pads.ports['C'], center_electrode.ports["N1"], layer=layer))
    waveguides.add_ref(pr.route_quad(pads.ports['L'], left_electrode.ports["N1"], layer=layer))
    waveguides.add_ref(pr.route_quad(pads.ports['R'], right_electrode.ports["N1"], layer=layer))

    # label_anchor = (waveguides.bbox[0, 0], waveguides.bbox[1, 1]) # top left corner
    # waveguides.add_label(label_text, label_anchor, 1, anchor='sw', layer=layer)

    label_text = ''
    if device_parameters.shorted:
        label_text += "shorted"
    if device_parameters.unetched:
        if label_text: label_text += ","
        label_text += "unetched"
    if device_parameters.off_defect:
        if label_text: label_text += ","
        label_text += "off_defect"
    if not label_text:
        label_text = "on_defect"

    label = waveguides.add_ref(pg.text(text=label_text, justify='center', size=40, layer=layer))
    label.move(destination=(0, 470))

    coordinate_text = waveguides.add_ref(pg.text(text=coordinates, justify='left', size=50, layer=layer))
    coordinate_text.rotate(-90, coordinate_text.center)
    coordinate_text.move(destination=(270,350))
    
    waveguides.rotate(45, waveguides.center)
    
    return waveguides

def main():
    device_parameters = DeviceParameters(
        total_length   = 40,
        crystal_length  = 0.6 + 0.03,
        crystal_width = 0.77,
        crystal_count  = 5,
        lattice_constant= 0.92,
        bridge_width   = 0.180 + 0.045,
        defect_width  = 0.9,
        defect_length   = 0.515,
        outline_width  = 0.3,
        electrode_overlap=0.1, 
        external_electrode_width=1.92,
        external_electrode_skew=5,
    )

    def device_parameters_factory(device_parameters_o: DeviceParameters, i: int):
        device_parameters=copy.copy(device_parameters_o)
        device_parameters.defect_length += i*0.015
        return device_parameters

    layout = Device()

    normal = (0, 0, 0)
    off_defect = (0, 0, 1)
    shorted = (1, 0, 0)
    unetched = (1, 1, 0)

    columns = [normal, off_defect, shorted, unetched]

    for i in range(8):
        (device_parameters.shorted, device_parameters.unetched, device_parameters.off_defect) = columns[floor(i/2)]
        for j in range(8):
            cell = layout.add_ref(generate_waveguides(
                device_count=10, 
                device_spacing=20, 
                gap_spacing=25, 
                device_parameters=device_parameters,
                layer=2, 
                device_parameters_factory=device_parameters_factory,
                coordinates=f"({i},{j})"
            ))
            cell.move(destination=(600*i, 1000*j + (i%2)*500))


    # quickplot(layout)
    layout.write_gds("out.gds")



if __name__ == "__main__":
    main()