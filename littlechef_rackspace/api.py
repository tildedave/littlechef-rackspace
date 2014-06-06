from libcloud.compute.base import NodeImage, NodeSize
from libcloud.compute.drivers.openstack import OpenStackNetwork
from libcloud.compute.providers import get_driver
from libcloud.compute.types import Provider, NodeState
import time
from lib import Host


class RackspaceApi(object):

    def __init__(self, username, key, region):
        self.username = username
        self.key = key
        self.region = region

    def _get_conn(self):
        Driver = get_driver(Provider.RACKSPACE)
        return Driver(self.username, self.key, region=self.region)

    def list_images(self):
        conn = self._get_conn()

        return [{"id": image.id, "name": image.name}
                for image in conn.list_images()]

    def list_networks(self):
        conn = self._get_conn()

        return [{"id": network.id, "name": network.name, "cidr": network.cidr}
                for network in conn.ex_list_networks()]

    def list_flavors(self):
        conn = self._get_conn()

        return [{"id": size.id, "name": size.name}
                for size in conn.list_sizes()]

    def list_servers(self):
        conn = self._get_conn()

        return [{"id": server.id,
                 "name": server.name,
                 "public_ipv4": server.public_ips[0]}
                for server in conn.list_nodes()]

    def _node_to_host(self, node):
        # Dumb hack to not select the ipv6 address
        public_ipv4_address = [ip for ip in node.public_ips
                               if ":" not in ip][0]

        return Host(name=node.name,
                    ip_address=public_ipv4_address)

    def _wait_for_node_to_become_active_host(self, conn, node, progress):
        while node.state != NodeState.RUNNING:
            time.sleep(5)

            if progress:
                progress.write(".")
            node = conn.ex_get_node_details(node.id)

        host = self._node_to_host(node)
        if progress:
            progress.write("\n")
            progress.write("Node active! (host: {0})\n"
                           .format(host.ip_address))

        return host

    def create_node(self, image, flavor, name, public_key_file,
                    networks=None, progress=None):
        create_kwargs = {}
        if networks:
            fake_networks = [OpenStackNetwork(n, None, None, self)
                             for n in networks]
            create_kwargs['networks'] = fake_networks

        conn = self._get_conn()
        fake_image = NodeImage(id=image, name=None, driver=conn)
        fake_flavor = NodeSize(id=flavor, name=None, ram=None, disk=None,
                               bandwidth=None, price=None, driver=conn)

        if progress:
            progress.write("Creating node {0} (image: {1}, flavor: {2})...\n"
                           .format(name, image, flavor))

        node = conn.create_node(name=name, image=fake_image,
                                size=fake_flavor, ex_files={
                                    "/root/.ssh/authorized_keys":
                                    public_key_file.read()
                                },
                                **create_kwargs)
        password = node.extra.get("password")

        if progress:
            progress.write("Created node {0} (id: {1}, password: {2})\n"
                           .format(name, node.id, password))
            progress.write("Waiting for node to become active")

        return self._wait_for_node_to_become_active_host(conn,
                                                         node,
                                                         progress=progress)

    def rebuild_node(self, name, image, public_key_file,
                     networks=None, progress=None):
        conn = self._get_conn()

        nodes_with_name = [n for n in conn.list_nodes() if n.name == name]
        node = nodes_with_name[0]
        fake_image = NodeImage(id=image, name=None, driver=conn)

        conn.ex_rebuild(node=node, image=fake_image, ex_files={
            "/root/.ssh/authorized_keys":
            public_key_file.read()
        })

        if progress:
            progress.write("Rebuilding node {0} ({1})...".format(node.name,
                                                                 node.id))
            progress.write("\n")
            progress.write("Waiting for node to become active")

        return self._wait_for_node_to_become_active_host(conn,
                                                         node,
                                                         progress=progress)
