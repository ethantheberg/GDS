from dataclasses import dataclass
from phidl import Device, set_quickplot_options
from phidl import quickplot
import phidl.geometry as pg
import phidl.routing as pr
set_quickplot_options(blocking=True, show_subports=True)

#vanadium-1
#gold-2
#removed GaAs - 3
#crystal blank - 8

@dataclass
class CrystalParameters:
    crystal_width: float
    crystal_height: float
    bridge_width: float
    bridge_length: float
    defect_width: float
    defect_height: float

    crystal_count: int
    outline_width: float

    crystal_layer: int
    outline_layer: int

    def total_length(self) -> float:
        return self.bridge_length * (self.crystal_count + 1) + self.crystal_width * (self.crystal_count - 1) + self.defect_width

@dataclass
class DeviceParameters:
    total_length: float
    crystal_parameters: CrystalParameters
    electrode_overlap: float
    external_electrode_width: float
    external_electrode_skew: float

    electrode_layer: int

def generate_photonic_crystal(parameters: CrystalParameters):
    photonic_crystal = Device("Photonic Crystal")

    bridge = pg.straight((parameters.bridge_width, parameters.bridge_length), parameters.crystal_layer)
    defect = pg.straight((parameters.defect_height, parameters.defect_width), parameters.crystal_layer)
    crystal = pg.straight((parameters.crystal_height, parameters.crystal_width), parameters.crystal_layer)

    origin = photonic_crystal.add_ref(bridge)
    origin.rotate(90, center=origin.origin)
    photonic_crystal.add_port(name=1, port=origin.ports[1])

    prev = origin
    for i in range(0, parameters.crystal_count * 2):
        if i % 2 == 1:
            next = photonic_crystal.add_ref(bridge)
        elif i == parameters.crystal_count - 1:
            next = photonic_crystal.add_ref(defect)
        else:
            next = photonic_crystal.add_ref(crystal)
        next.connect(port=1, destination=prev.ports[2])
        prev = next
    photonic_crystal.add_port(name=2, port=next.ports[2])

    outline = pg.outline(photonic_crystal, parameters.outline_width, layer=parameters.outline_layer)

    for i in [1,2]:
        end_uncover = photonic_crystal.add_ref(pg.straight((parameters.crystal_height+parameters.outline_width, parameters.outline_width)))
        end_uncover.connect(1, photonic_crystal.ports[i])
        
        outline = pg.boolean(outline, end_uncover, operation='NOT', layer=parameters.outline_layer)

    photonic_crystal.remove(end_uncover)

    photonic_crystal.add_ref(outline)

    return photonic_crystal

def generate_device(parameters: DeviceParameters):
    assert parameters.crystal_parameters.crystal_count % 2 == 1

    device = Device()

    crystal = generate_photonic_crystal(parameters.crystal_parameters)
    device.add_ref(crystal)

    crystal_length = parameters.crystal_parameters.total_length()

    internal_electrode_width = max(parameters.crystal_parameters.crystal_height, parameters.crystal_parameters.defect_height)
    internal_electrode_length = (crystal_length - parameters.crystal_parameters.defect_width)/2 + parameters.electrode_overlap
    internal_electrode = pg.straight((internal_electrode_width, internal_electrode_length), layer=parameters.electrode_layer)

    for i in [1,2]:
      internal_electrode_i = crystal.add_ref(internal_electrode)
      internal_electrode_i.connect(port=i, destination=crystal.ports[i])
      internal_electrode_i.rotate(180, internal_electrode_i.ports[i].center)

    external_electrode_length = (parameters.total_length - crystal_length)/2
    connector = pg.connector(width=parameters.external_electrode_width)
    
    for i in [1, 2]:
      external_connector_i = crystal.add_ref(connector)
      external_connector_i.move(external_connector_i.origin, crystal.ports[i].center + (external_electrode_length * (1 if i == 2 else -1), -parameters.external_electrode_skew))
      
      external_electrode = crystal.add_ref(pr.route_quad(crystal.ports[i], external_connector_i.ports[i%2+1], parameters.external_electrode_width, layer=parameters.electrode_layer))
      
      device.add_port("W" if i==1 else "E", port=external_connector_i.ports[i%2+1])
    
    return device

def generate_waveguides(
    device_count: int,
    device_spacing: float,
    gap_spacing: float,
    device_parameters: DeviceParameters,
    layer: int
):
    waveguides = Device()
    electrode_height = device_count*device_spacing
    center_electrode = waveguides.add_ref(pg.compass_multi((50, electrode_height), {"N": 1, "E": device_count, "W": device_count}, layer=layer))

    device = generate_device(device_parameters)

    for i in range(device_count):
        pass
        device_i = waveguides.add_ref(device)
        device_i.connect("E", center_electrode.ports[f"W{device_count-i}"], overlap=(device_parameters.total_length-gap_spacing)/2)
        device_i = waveguides.add_ref(device)
        device_i.connect("W", center_electrode.ports[f"E{device_count-i}"], overlap=(device_parameters.total_length-gap_spacing)/2)

    side_electrode = pg.straight((30, electrode_height), layer=layer)
    left_electrode = waveguides.add_ref(side_electrode)
    left_electrode.move(left_electrode.center, center_electrode.center-(gap_spacing+40, 0))

    right_electrode = waveguides.add_ref(side_electrode)
    right_electrode.move(right_electrode.center, center_electrode.center+(gap_spacing+40, 0))

    bottom_route = waveguides.add_ref(pr.route_sharp(left_electrode.ports[2], right_electrode.ports[2], 30, layer=layer))

    waveguides.add_port('L', port=left_electrode.ports[1])
    waveguides.add_port('C', port=center_electrode.ports["N1"])
    waveguides.add_port('R', port=right_electrode.ports[1])

    return waveguides

def generate_pads(
    device_count: int,
    device_spacing: float,
    gap_spacing: float,
    device_parameters: DeviceParameters,
    layer: int
):
    cell = Device()
    pads = Device()

    pad = pg.straight((150, 150), layer=layer)

    left_pad = pads.add_ref(pad)
    center_pad = pads.add_ref(pad)
    right_pad = pads.add_ref(pad)

    pads.distribute(spacing=75)

    left_pad_top = pads.add_ref(pg.compass_multi((150, 120), ports={'E': 2, 'S': 1}, layer=layer))
    left_pad_top.connect('S1', left_pad.ports[1])

    right_pad_top = pads.add_ref(pg.compass_multi((150, 120), ports={'W': 2, 'S': 1}, layer=layer))
    right_pad_top.connect('S1', right_pad.ports[1])

    top_connection = pads.add_ref(pr.route_quad(right_pad_top.ports['W2'], left_pad_top.ports['E2'], layer=layer))

    pads.add_port("L", port=left_pad.ports[2])
    pads.add_port("C", port=center_pad.ports[2])
    pads.add_port("R", port=right_pad.ports[2])


    waveguides = cell.add_ref(generate_waveguides(device_count, device_spacing, gap_spacing, device_parameters, layer))
    pads_r = cell.add_ref(pads)

    pads_r.connect('C', waveguides.ports['C'], -100)

    cell.add_ref(pr.route_quad(pads_r.ports['C'], waveguides.ports['C'], layer=layer))

    cell.add_ref(pr.route_quad(pads_r.ports['L'], waveguides.ports['L'], layer=layer))
    cell.add_ref(pr.route_quad(pads_r.ports['R'], waveguides.ports['R'], layer=layer))

    return cell
    
def main():
    crystal_parameters = CrystalParameters(
        crystal_width=0.6,
        crystal_height=0.77,
        crystal_count=11,
        bridge_length=0.32,
        bridge_width=0.18,
        defect_height=0.9,
        defect_width=0.545,
        outline_width=0.3,
        crystal_layer=8,
        outline_layer=3
    )

    device_parameters = DeviceParameters(
        total_length=40,
        crystal_parameters = crystal_parameters,
        electrode_overlap=0.15, 
        external_electrode_width=1.92,
        external_electrode_skew=5,
        electrode_layer=1
    )

    cell = generate_pads(
        device_count=5, 
        device_spacing=20, 
        gap_spacing=25, 
        device_parameters=device_parameters,
        layer=2
    )

    quickplot(cell)
    cell.write_gds("out.gds")



if __name__ == "__main__":
    main()