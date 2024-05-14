import argparse
import itertools
import os
import re
import sys
from collections import defaultdict

import executable
import utils
import workflow
import yaml
from logger import logger
from workflow import TaskConfig

PATH = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def main(args: argparse.Namespace) -> None:
    url = utils.trim(text=args.url)
    if not url:
        logger.error("please provide the url for the subscriptions")
        return

    filename = utils.trim(args.filename)
    if not filename:
        logger.error(f"must specify the file path where the results will be saved")
        return

    content = utils.http_get(url=url, timeout=30)
    auto_groups = re.findall(r"^https?://\S+", content, flags=re.M)
    if not auto_groups:
        logger.warning("cannot found any valid crawler subscription")
        auto_groups = []

    manual_url = utils.trim(text=args.manual_url)
    manual_content = utils.http_get(url=manual_url, timeout=30)
    manual_groups = re.findall(r"^https?://\S+", manual_content, flags=re.M)
    if not manual_groups:
        logger.warning("cannot found any valid manual subscription")
        manual_groups = []
    else:
        for sub in set(manual_groups):
            logger.info(f"found {sub} in manual subscription")

    groups = auto_groups + manual_groups
    if len(groups) < 1:
        logger.warning("cannot found any valid subscription")
        return

    _, subconverter_bin = executable.which_bin()
    tasks, subscriptions = [], set(groups)
    for sub in subscriptions:
        conf = TaskConfig(name=utils.random_chars(length=8), sub=sub, bin_name=subconverter_bin, special_protocols=args.special_protocols)
        tasks.append(conf)

    logger.info(f"start generate subscribes information, all tasks: {len(tasks)}, manual tasks: {len(manual_groups)}")
    generate_conf = os.path.join(PATH, "subconverter", "generate.ini")
    if os.path.exists(generate_conf) and os.path.isfile(generate_conf):
        os.remove(generate_conf)

    results = utils.multi_thread_run(func=workflow.execute, tasks=tasks, num_threads=args.num)
    proxies = list(itertools.chain.from_iterable(results))

    if len(proxies) == 0:
        logger.error("exit because cannot fetch any proxy node")
        sys.exit(0)

    filepath = os.path.abspath(filename)
    directory = os.path.dirname(filepath)
    os.makedirs(directory, exist_ok=True)

    # remove unused key
    nodes = []
    for p in proxies:
        if not isinstance(p, dict):
            continue

        for k in ["sub", "chatgpt", "liveness"]:
            p.pop(k, None)

        nodes.append(p)
        
    unique_nodes, unique_node_tags = [], set()
    for node in nodes:
        # 将字典转换为元组，确保所有元素都是可哈希的
        node_tag = tuple((k, str(v)) for k, v in node.items() if k not in ['name', 'uuid'])
        if node_tag not in unique_node_tags:
            unique_node_tags.add(node_tag)
            unique_nodes.append(node)
    logger.info(f"Number of deduplicated proxies: {len(nodes) - len(unique_nodes)}")
    nodes = unique_nodes

    # 记录每个名称出现的次数
    name_count = defaultdict(int)
    # 存储要重命名的索引
    to_rename = []
    # 遍历每个代理配置
    for idx, proxy in enumerate(nodes):
        name = proxy['name']
        name_count[name] += 1
        if name_count[name] > 1:
            to_rename.append((idx, f"{name}_{name_count[name]}"))

    # 重命名重复的名称
    for idx, new_name in to_rename:
        nodes[idx]['name'] = new_name

    data = {"proxies": nodes}
    with open(filepath, "w+", encoding="utf8") as f:
        yaml.dump(data, f, allow_unicode=True)
        logger.info(f"found {len(nodes)} proxies, renamed {len(to_rename)} proxies, save it to {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--filename",
        type=str,
        required=False,
        default="proxies.yaml",
        help="file path to save merged proxies",
    )

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=64,
        help="threads num for concurrent fetch proxy",
    )

    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=False,
        default=os.environ.get("EXISTS_LINK", ""),
        help="subscriptions link",
    )

    parser.add_argument(
        "-m",
        "--manual_url",
        type=str,
        required=False,
        default=os.environ.get("MANUAL_EXISTS_LINK", ""),
        help="manual subscriptions link",
    )

    parser.add_argument(
        "-s",
        "--special_protocols",
        type=int,
        required=False,
        default=True,
        help="if use special protocols",
    )

    main(args=parser.parse_args())
