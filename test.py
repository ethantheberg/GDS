from math import ceil, floor
from phidl import Device, Group, set_quickplot_options
from phidl import quickplot
import phidl.geometry as pg
import phidl.routing as pr

set_quickplot_options(blocking=True, show_subports=False)

def photonic_crystal(
    crystal_width,
    crystal_height,
    bridge_width,
    bridge_length,
    crystal_count,
    defect_width,
    defect_height,
    outline_width,
):
    photonic_crystal = Device("Photonic Crystal")

    bridge = pg.straight((bridge_width, bridge_length))
    defect = pg.straight((defect_height, defect_width))
    crystal = pg.straight((crystal_height, crystal_width))

    origin = photonic_crystal.add_ref(bridge)
    photonic_crystal.add_port(name=1, port=origin.ports[1])

    prev = origin
    for i in range(0, crystal_count * 2):
        if i % 2 == 1:
            next = photonic_crystal.add_ref(bridge)
        elif i == crystal_count - 1:
            next = photonic_crystal.add_ref(defect)
        else:
            next = photonic_crystal.add_ref(crystal)
        next.connect(port=1, destination=prev.ports[2])
        prev = next
    photonic_crystal.add_port(name=2, port=next.ports[2])

    outline = pg.outline(photonic_crystal, outline_width, layer=1)
    photonic_crystal.add_ref(outline)

    return photonic_crystal




def photonic_crystal_electrodes(
    total_length, 
    crystal_width,
    crystal_height,
    bridge_width,
    bridge_length,
    crystal_count,
    defect_width,
    defect_height,
    outline_width,
    electrode_overlap,
    external_electrode_width, 
    external_electrode_skew,  
):
    assert crystal_count % 2 == 1

    crystal = photonic_crystal(
        crystal_width,
        crystal_height,
        bridge_width,
        bridge_length,
        crystal_count,
        defect_width,
        defect_height,
        outline_width
    )

    crystal_length = bridge_length * (crystal_count + 1) + crystal_width * (crystal_count - 1) + defect_width

    internal_electrode_width = max(crystal_height, defect_height)
    internal_electrode_length = floor(crystal_count/2)*(crystal_width+bridge_length) + bridge_length + electrode_overlap
    internal_electrode = pg.straight((internal_electrode_width, internal_electrode_length), layer=2)

    for i in [1,2]:
      internal_electrode_i = crystal.add_ref(internal_electrode)
      internal_electrode_i.connect(port=i, destination=crystal.ports[i])
      internal_electrode_i.rotate(180, internal_electrode_i.ports[i].center)

    external_electrode_length = (total_length - crystal_length)/2
    connector = pg.connector(width=external_electrode_width, orientation=90)
    
    for i in [1, 2]:
      external_connector_i = crystal.add_ref(connector)
      external_connector_i.move(external_connector_i.origin, crystal.ports[i].center + (external_electrode_skew, external_electrode_length * (-1 if i == 2 else 1)))
      
      external_electrode = crystal.add_ref(pr.route_quad(crystal.ports[i], external_connector_i.ports[i%2+1], external_electrode_width, layer=2))
      
      crystal.ports[i]=external_connector_i.ports[i]
    
    return crystal

quickplot(
    photonic_crystal_electrodes(
        total_length=200,
        crystal_width=5,
        crystal_height=5,
        crystal_count=9,
        bridge_length=2,
        bridge_width=2,
        defect_height=7,
        defect_width=4,
        outline_width=3,
        electrode_overlap=1, 
        external_electrode_width=10,
        external_electrode_skew=10
    )
)