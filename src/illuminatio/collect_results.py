import click
import csv
import locale
import os
import os.path
import yaml


@click.command()
@click.option('--directory', '-d', help='Root directory of results that are to be collected.')
@click.option('--outfile', '-o', help='File to write aggregated results to.')
@click.option('--performance/--tests', '-p/-t', default=True,
              help='Whether to collect performance results or test results')
@click.option('--delimiter', default=';')
@click.option('--quotechar', default='"')
def cli(directory, outfile, delimiter, quotechar, performance):
    locale.setlocale(locale.LC_ALL, '')
    if directory is None or not os.path.exists(directory):
        click.echo("directory must be an exisiting directory")
        exit(1)
    if outfile is None:
        click.echo("outfile must be set")
        exit(1)
    found_files = {}
    for dpath, _, fnames in os.walk(directory):
        yaml_files = [os.path.join(dpath, fname) for fname in fnames if
                      fname.endswith(".yaml") or fname.endswith(".yml")]
        for yaml_file in yaml_files:
            with open(yaml_file) as yam:
                found_files[yaml_file] = yaml.safe_load(yam)
    os.makedirs(os.path.abspath(os.path.join(outfile, os.pardir)), exist_ok=True)
    with open(outfile, mode='w') as csvFile:
        writer = csv.writer(csvFile, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
        if performance:
            run_times = {k.replace(directory, ""): v["runtimes"] for k, v in found_files.items()}
            title_line = ["fileName", "rawTitle"]
            lines = []
            for file_name, runtime_dict in run_times.items():
                # add more column names if we have multiple files, this code assumes same depth for every found file
                if len(title_line) <= 2 and "/" in file_name:
                    additional_col_titles = extract_titles_from(file_name)
                    title_line.extend(additional_col_titles)
                for name, value_or_dict in runtime_dict.items():
                    line = [file_name, name]
                    additional_cols = extract_values_from(file_name)
                    line.extend(additional_cols)
                    if isinstance(value_or_dict, dict):
                        for keyList, value in flatten(value_or_dict):
                            if value != "error":
                                lines.append(line + [locale.str(value)] + keyList)
                            else:
                                lines.append(line + [value] + keyList)
                    else:
                        line.append(locale.str(value_or_dict))
                        lines.append(line)
            title_line.append("time")
            writer.writerow(title_line)
            for line in lines:
                writer.writerow(line)
        else:
            test_results = {k.replace(directory, ""): v["cases"] for k, v in found_files.items()}
            title_line = ["fileName"]
            value_titles = ["from", "to", "port", "resultName", "result"]
            lines = []
            for file_name, result_dict in test_results.items():
                if len(title_line) <= 1 and "/" in file_name:
                    title_line.extend(extract_titles_from(file_name))
                file_name_values = extract_values_from(file_name)
                for keyList, value in flatten(result_dict):
                    lines.append([file_name] + file_name_values + keyList + [value])
            writer.writerow(title_line + value_titles)
            for line in lines:
                writer.writerow(line)


def extract_values_from(fname):
    return [w.split("_")[0] if "_" in w else w for w in fname.split("/")]


def extract_titles_from(fname):
    return [w.split("_")[1].replace(".yaml", "") if "_" in w else str(i) for i, w in enumerate(fname.split("/"))]


def flatten(d, key_list=None):
    if key_list is None:
        key_list = []
    if isinstance(d, dict):
        for k in d:
            yield from flatten(d[k], key_list + [k])
    else:
        yield key_list, d


# pylint: disable=E1120
if __name__ == '__main__':
    cli()
# pylint: enable=E1120
