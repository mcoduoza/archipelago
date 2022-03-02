import sys
import os
from typing import Dict, List, Set, Union
from enum import Enum
from graphviz import Digraph

class RouteType(Enum):
    SB=1
    RMUX=2
    PORT=3
    REG=4

class RouteNode:
    def __init__(self, x, y, route_type=None, track=None,
                 side=None, io=None, bit_width=None, port=None, net_id=None,
                 reg_name=None, rmux_name=None, reg=False, kernel=None):
        
        assert x is not None
        self.x = x
        assert y is not None
        self.y = y
        
        self.tile_id = f"{route_type or 0},{x or 0},{y or 0},"+\
            f"{track or 0},{side or 0},{io or 0},{bit_width or 0},{port or 0},"+\
            f"{net_id or 0},{reg_name or 0},{rmux_name or 0},{reg}"
        assert self.tile_id is not None

        if route_type == "SB":
            self.route_type = RouteType.SB
        elif route_type == "RMUX":
            self.route_type = RouteType.RMUX
        elif route_type == "PORT":
            self.route_type = RouteType.PORT
        elif route_type == "REG":
            self.route_type = RouteType.REG

        assert self.route_type is not None

        self.track = track
        self.side = side
        self.io = io
        self.bit_width = bit_width
        self.port = port
        self.net_id = net_id
        self.reg_name = reg_name
        self.rmux_name = rmux_name
        self.reg = reg
        self.kernel = kernel

    def update_tile_id(self):
        self.tile_id = f"{self.type_ or 0},{self.route_type or 0},"+\
                        f"{self.x or 0},{self.y or 0},{self.track or 0},"+\
                        f"{self.side or 0},{self.io or 0},"+\
                        f"{self.bit_width or 0},{self.port or 0},"+\
                        f"{self.net_id or 0},{self.reg_name or 0},"+\
                        f"{self.rmux_name or 0},{self.reg}"
        assert self.tile_id is not None

    def to_route(self):
        if self.route_type == RouteType.SB:
            route_string = f"{self.route_type} ({self.track}, {self.x}, "+\
                           f"{self.y}, {self.side}, {self.io}, {self.bit_width})"
        elif self.route_type == RouteType.PORT:
            route_string = f"{self.route_type} ({self.port}, {self.x}, "+\
                           f"{self.y}, {self.bit_width})"
        elif self.route_type == RouteType.REG:
            route_string = f"{self.route_type} ({self.reg_name}, {self.track}, "+\
                           f"{self.x}, {self.y}, {self.bit_width})"
        elif self.route_type == RouteType.RMUX:
            route_string = f"{self.route_type} ({self.rmux_name}, {self.x}, "+\
                           f"{self.y}, {self.bit_width})"
        else:
            raise ValueError("Unrecognized route type")
        return route_string

    def __repr__(self):
        return f"{self.tile_id}"

    def __eq__(self, other):
        return self.tile_id == other.tile_id

    def __hash__(self):
        return hash(self.tile_id)

class TileType(Enum):
    PE=1
    MEM=2
    REG=3
    POND=4
    IO16=5
    IO1=6

class TileNode:
    def __init__(self, x, y, tile_id, kernel):
        
        self.x = x
        self.y = y
        
        self.tile_id = tile_id

        if self.tile_id[0] == 'p':
            self.tile_type = TileType.PE
        elif self.tile_id[0] == 'm':
            self.tile_type = TileType.MEM
        elif self.tile_id[0] == 'M':
            self.tile_type = TileType.POND
        elif self.tile_id[0] == 'r':
            self.tile_type = TileType.REG
        elif self.tile_id[0] == 'I':
            self.tile_type = TileType.IO16
        elif self.tile_id[0] == 'i':
            self.tile_type = TileType.IO1

        self.kernel = kernel

        self.input_port_latencies = {}
        self.input_port_break_path = {}

    def __repr__(self):
        return f"{self.tile_id}"

    def __eq__(self, other):
        return self.tile_id == other.tile_id

    def __hash__(self):
        return hash(self.tile_id)

class RoutingResultGraph:
    def __init__(self):
        self.nodes: List[Union[RouteNode, TileNode]] = []
        self.tile_id_to_tile: Dict[str, Union[RouteNode, TileNode]] = {}
        self.edges: List[(Union[RouteNode, TileNode], Union[RouteNode, TileNode])] = []
        self.edge_weights: Dict[(Union[RouteNode, TileNode], Union[RouteNode, TileNode]), int] = {}
        self.inputs: List[Union[RouteNode, TileNode]] = []
        self.outputs: List[Union[RouteNode, TileNode]] = []
        self.sources: Dict[Union[RouteNode, TileNode], List[Union[RouteNode, TileNode]]] = {}
        self.sinks: Dict[Union[RouteNode, TileNode], List[Union[RouteNode, TileNode]]] = {}
        self.node_latencies: Dict[Union[RouteNode, TileNode], int] = {} 
        self.placement = {}
        self.id_to_ports = {}
        self.id_to_name: Dict[str, str] = {}
        self.added_regs = 0
        self.mems = None
        self.pes = None
        self.ponds = None
        self.input_ios = None
        self.output_ios = None
        self.regs = None
        self.shift_regs = None
        self.roms = None

    def get_tile(self, tile_id):
        if tile_id in self.tile_id_to_tile:
            return self.tile_id_to_tile[tile_id]
        return None        

    def get_tiles(self):
        tiles = []
        for node in self.nodes:
            if isinstance(node, TileNode):
                tiles.append(node)
        return tiles

    def get_routes(self):
        routes = []
        for node in self.nodes:
            if isinstance(node, RouteNode):
                routes.append(node)
        return routes

    def get_mems(self):
        if not self.mems:
            mems = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.MEM:
                    mems.append(node)
            self.mems = mems
        return self.mems

    def get_roms(self):
        if not self.roms:
            mems = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.MEM:
                    rom = False
                    for source in self.sources[node]:
                        if self.get_node(source).port == "ren_in_0":
                            rom = True
                            break
                    if rom:
                        mems.append(node)
            self.roms = mems
        return self.roms

    def get_regs(self):
        if not self.regs:
            regs = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.REG:
                    regs.append(node)
            self.regs = regs
        return self.regs

    def get_shift_regs(self):
        if not self.shift_regs:
            regs = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.MEM \
                   and "d_reg_" in self.id_to_name[node.tile_id]:
                    regs.append(node)
            self.shift_regs = regs
        return self.shift_regs

    def get_ponds(self):
        if not self.ponds:
            ponds = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.POND:
                    ponds.append(node)
            self.ponds = ponds
        return self.ponds

    def get_pes(self):
        if not self.pes:
            pes = []
            for node in self.nodes:
                if isinstance(node, TileNode) and node.tile_type == TileType.POND:
                    pes.append(node)
            self.pes = pes
        return self.pes

    def get_input_ios(self):
        if not self.input_ios:
            ios = []
            for node in self.nodes:
                if isinstance(node, TileNode) and (node.tile_type == TileType.IO16 \
                   or node.tile_type == TileType.IO1) and len(self.sources[node]) == 0:
                    ios.append(node)
            self.input_ios = ios
        return self.input_ios

    def get_output_ios(self):
        if not self.output_ios:
            ios = []
            for node in self.nodes:
                if isinstance(node, TileNode) and (node.tile_type == TileType.IO16 \
                   or node.tile_type == TileType.IO1) and len(self.sinks[node]) == 0:
                    ios.append(node)
            self.output_ios = ios
        return self.output_ios

    def is_reachable(self, source, dest):
        visited = set()
        queue = []

        queue.append(source)
        visited.add(source)

        while queue:
            n = queue.pop()

            if n == dest:
                return True

            for node in self.sinks[n]:
                if node not in visited:
                    queue.append(node)
                    visited.add(node)
        return False

    def add_node(self, node):
        if node not in self.nodes:
            self.nodes.append(node)
        if isinstance(node, TileNode):
            self.tile_id_to_tile[node.tile_id] = node

    def add_edge(self, node1, node2):
        assert node1 in self.nodes, f"{node1} not in nodes"
        assert node2 in self.nodes, f"{node2} not in nodes"

        assert isinstance(node1, RouteNode) or isinstance(node1, TileNode)
        assert isinstance(node2, RouteNode) or isinstance(node2, TileNode)

        if (node1, node2) not in self.edges:
            self.edges.append((node1, node2))

        if node2 not in self.sources:
            self.sources[node2] = []
        if node1 not in self.sources[node2]:
            self.sources[node2].append(node1)

        if node1 not in self.sinks:
            self.sinks[node1] = []
        if node2 not in self.sinks[node1]:
            self.sinks[node1].append(node2)

    def update_sources_and_sinks(self):
        self.inputs = []
        self.outputs = []

        for node in self.nodes:
            self.sources[node] = []
            self.sinks[node] = []

        for source, sink in self.edges:
            assert isinstance(source, RouteNode) or isinstance(source, TileNode)
            assert isinstance(sink, RouteNode) or isinstance(sink, TileNode)
            self.sources[sink].append(source)
            self.sinks[source].append(sink)

        for node in self.nodes:
            if len(self.sources[node]) == 0:
                self.inputs.append(node)
            if len(self.sinks[node]) == 0:
                self.outputs.append(node)

    def topological_sort(self):
        visited = set()
        stack = []
        for n in self.inputs:
            if n not in visited:
                self.topological_sort_helper(n, stack, visited)
        return stack[::-1]

    def topological_sort_helper(self, node, stack, visited):
        visited.add(node)
        for ns in self.sinks[node]:
            if ns not in visited:
                self.topological_sort_helper(ns, stack, visited)
        stack.append(node)

    def remove_edge(self, edge):
        node0 = edge[0]
        node1 = edge[1]

        if edge in self.edges:
            self.edges.remove(edge)
        if node0 in self.sources[node1]:
            self.sources[node1].remove(node0)
        if node1 in self.sinks[node0]:
            self.sinks[node0].remove(node1)

    def is_cyclic_util(self, v, visited, rec_stack):
        visited.append(v)
        rec_stack.append(v)

        for neighbour in self.sinks[v]:
            if neighbour not in visited:
                retval = self.is_cyclic_util(neighbour, visited, rec_stack)
                if retval != None:
                    return retval
            elif neighbour in rec_stack:
                return (v, neighbour)

        rec_stack.remove(v)
        return None

    def fix_cycles(self):
        sys.setrecursionlimit(10**5)
        visited = []
        rec_stack = []
        for node in self.inputs:
            if node not in visited:
                break_edge = self.is_cyclic_util(node, visited, rec_stack)
                if break_edge is not None:
                    self.remove_edge(break_edge)
                    return True
        return False

    def segment_to_node(self, segment, net_id):
        if segment[0] == "SB":
            track, x, y, side, io_, bit_width = segment[1:]
            node = RouteNode(x, y, route_type="SB", track=track,
                        side=side, io=io_, bit_width=bit_width, net_id=net_id)
        elif segment[0] == "PORT":
            port_name, x, y, bit_width = segment[1:]
            node = RouteNode(x, y, route_type="PORT",
                        bit_width=bit_width, net_id=net_id, port=port_name)
        elif segment[0] == "REG":
            reg_name, track, x, y, bit_width = segment[1:]
            node = RouteNode(x, y, route_type="REG", track=track,
                        bit_width=bit_width, net_id=net_id, reg_name=reg_name)
        elif segment[0] == "RMUX":
            rmux_name, x, y, bit_width = segment[1:]
            node = RouteNode(x, y, route_type="RMUX",
                        bit_width=bit_width, net_id=net_id, rmux_name=rmux_name)
        else:
            raise ValueError("Unrecognized route type")
        return node

    def gen_placement(self, placement, netlist):

        for net_id, conns in netlist.items():
            for conn in conns:
                if conn[0] not in self.id_to_ports:
                    self.id_to_ports[conn[0]] = []
                self.id_to_ports[conn[0]].append(conn[1])       

        for blk_id, place in placement.items():
            if place not in self.placement:
                self.placement[place] = []
            self.placement[place].append(blk_id)

    def get_tile_at(self, x, y, port):
        tiles = self.placement[(x,y)]

        for tile in tiles:
            if port in self.id_to_ports[tile]:
                return tile
        
        return None

    def get_reg_at(self, x, y):
        tiles = self.placement[(x,y)]

        for tile in tiles:
            if tile[0] == 'r':
                return tile
        
        return None

    def update_edge_kernels(self):
        for in_node in self.inputs:
            queue = []
            visited = set()
            kernel = in_node.kernel
            queue.append(in_node)
            visited.add(in_node)
            while queue:
                n = queue.pop()
                kernel = n.kernel

                for node in self.sinks[n]:
                    if node not in visited:
                        queue.append(node)
                        visited.add(node)
                        if isinstance(node, RouteNode):
                            node.kernel = kernel

        for tile in self.get_tiles():
            for source in self.sources[tile]:
                source.kernel = tile.kernel

    def print_graph(self, filename, edge_weights = False):
        g = Digraph()
        for node in self.nodes:
            g.node(str(node), label = str(node))

        for edge in self.edges:
            g.edge(str(edge[0]), str(edge[1]))
            
        g.render(filename=filename)

def construct_graph(placement, routes, id_to_name, netlist, pe_latency=0):
    graph = RoutingResultGraph()
    graph.id_to_name = id_to_name
    graph.gen_placement(placement, netlist)

    max_reg_id = 0

    for blk_id, place in placement.items():
        if len(graph.id_to_name[blk_id].split("$")) > 0:
            kernel = graph.id_to_name[blk_id].split("$")[0]
        else:
            kernel = None
        node = TileNode(place[0], place[1], tile_id=blk_id, kernel=kernel)
        graph.add_node(node)
        max_reg_id = max(max_reg_id, int(blk_id[1:]))
    graph.added_regs = max_reg_id + 1

    for net_id, net in routes.items():
        for route in net:
            for seg1, seg2 in zip(route, route[1:]):
                node1 = graph.segment_to_node(seg1, net_id)
                graph.add_node(node1)
                node2 = graph.segment_to_node(seg2, net_id)
                graph.add_node(node2)
                graph.add_edge(node1, node2)

                if node1.route_type == RouteType.PORT:
                    tile_id = graph.get_tile_at(node1.x, node1.y, node1.port)
                    graph.add_edge(graph.get_tile(tile_id), node1)
                elif node1.route_type == RouteType.REG:
                    tile_id = graph.get_reg_at(node1.x, node1.y)
                    graph.add_edge(graph.get_tile(tile_id), node1)

                if node2.route_type == RouteType.PORT:
                    tile_id = graph.get_tile_at(node2.x, node2.y, node2.port)
                    graph.add_edge(node2, graph.get_tile(tile_id))
                elif node2.route_type == RouteType.REG:
                    tile_id = graph.get_reg_at(node2.x, node2.y)
                    graph.add_edge(node2, graph.get_tile(tile_id))

    graph.update_sources_and_sinks()

    id_to_input_ports = {}
    for net_id, conns in netlist.items():
        for conn in conns[1:]:
            if conn[0] not in id_to_input_ports:
                id_to_input_ports[conn[0]] = []
            id_to_input_ports[conn[0]].append(conn[1])    

    for tile in graph.get_tiles():
        tile_id = tile.tile_id
        if tile_id in id_to_input_ports:
            for port in id_to_input_ports[tile_id]:
                if tile.tile_type == TileType.PE:
                    tile.input_port_latencies[port] = pe_latency
                    tile.input_port_break_path[port] = pe_latency != 0
                elif tile.tile_type == TileType.MEM:
                    if "flush" in port or "chain" in port:
                        tile.input_port_latencies[port] = 0
                        tile.input_port_break_path[port] = False
                    else:
                        tile.input_port_latencies[port] = 0
                        tile.input_port_break_path[port] = True
                elif tile.tile_type == TileType.REG:
                    if tile in graph.get_shift_regs():
                        tile.input_port_latencies[port] = 0
                        tile.input_port_break_path[port] = True
                    else:
                        tile.input_port_latencies[port] = 1
                        tile.input_port_break_path[port] = True
                elif tile.tile_type == TileType.POND:
                    tile.input_port_latencies[port] = 0
                    tile.input_port_break_path[port] = True
                elif tile.tile_type == TileType.IO1 or tile.tile_type == TileType.IO16:
                    tile.input_port_latencies[port] = 0
                    tile.input_port_break_path[port] = False

    graph.update_edge_kernels()

    while graph.fix_cycles():
        pass

    return graph