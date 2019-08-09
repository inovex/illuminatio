"""
Contains CLI functionalities to configure the collection of
either performance or test results
"""
import os
import os.path
import csv
import locale
import yaml
import click


@click.command()
@click.option('--directory', '-d', help='Root directory of results that are to be collected.')
@click.option('--outfile', '-o', help='File to write aggregated results to.')
@click.option('--performance/--tests', '-p/-t', default=True,
              help='Whether to collect performance results or test results')
@click.option('--delimiter', default=';')
@click.option('--quotechar', default='"')
def cli(directory, outfile, delimiter, quotechar, performance):
    """
    A command line function that grants several options on treating and displaying collected results
    """
    locale.setlocale(locale.LC_ALL, '')
    if directory is None or not os.path.exists(directory):
        click.echo("directory must be an existing directory")
        exit(1)
    if outfile is None:
        click.echo("outfile must be set")
        exit(1)
    found_files = {}
    for dpath, _, file_names in os.walk(directory):
        for yaml_file in [os.path.join(dpath, file_name) for file_name in file_names if \
                      file_name.endswith(".yaml") or file_name.endswith(".yml")]:
            with open(yaml_file) as yam:
                found_files[yaml_file] = yaml.safe_load(yam)
    os.makedirs(os.path.abspath(os.path.join(outfile, os.pardir)), exist_ok=True)
    with open(outfile, mode='w') as csv_file:
        writer = csv.writer(csv_file, delimiter=delimiter, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
        if performance:
            collect_performance_results(found_files, writer, directory)
        else:
            collect_test_results(found_files, writer, directory)

def collect_test_results(found_files, writer, directory):
    """
    Perform a run and collect test results
    """
    test_results = {k.replace(directory, ""): v["cases"] for k, v in found_files.items()}
    title_line = ["fileName"]
    value_titles = ["from", "to", "port", "resultName", "result"]
    lines = []
    for file_name, result_dict in test_results.items():
        if len(title_line) <= 1 and "/" in file_name:
            title_line.extend(extract_titles_from(file_name))
        file_name_values = extract_values_from(file_name)
        for key_list, value in flatten(result_dict):
            lines.append([file_name] + file_name_values + key_list + [value])
    writer.writerow(title_line + value_titles)
    for line in lines:
        writer.writerow(line)

def collect_performance_results(found_files, writer, directory):
    """
    Perform a run and collect performance results
    """
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
                for key_list, value in flatten(value_or_dict):
                    if value != "error":
                        lines.append(line + [locale.str(value)] + key_list)
                    else:
                        lines.append(line + [value] + key_list)
            else:
                line.append(locale.str(value_or_dict))
                lines.append(line)
    title_line.append("time")
    writer.writerow(title_line)
    for line in lines:
        writer.writerow(line)


def extract_values_from(file_name):
    """
    extracts values from a file
    """
    return [w.split("_")[0] if "_" in w else w for w in file_name.split("/")]


def extract_titles_from(file_name):
    """
    extracts titles from a file's name
    """
    return [w.split("_")[1].replace(".yaml", "") if "_" in w else str(i) for i, w in enumerate(file_name.split("/"))]

def flatten(dictionary, key_list=None):
    """
    retrieves the subdictionaries inside a dictionary to enable easy iteration
    """
    if key_list is None:
        key_list = []
    if isinstance(dictionary, dict):
        for key in dictionary:
            yield from flatten(dictionary[key], key_list + [key])
    else:
        yield key_list, dictionary


# pylint: disable=E1120
if __name__ == '__main__':
    cli()
# pylint: enable=E1120
