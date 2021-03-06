import pandas
import pytest
from flytekitplugins.hive.task import HiveConfig, HiveSelectTask, HiveTask

from flytekit import kwtypes, workflow
from flytekit.extend import Image, ImageConfig, SerializationSettings, get_serializable
from flytekit.testing import task_mock
from flytekit.types.schema import FlyteSchema


def test_serialization():
    hive_task = HiveTask(
        name="flytekit.demo.hive_task.hivequery1",
        inputs=kwtypes(my_schema=FlyteSchema, ds=str),
        config=HiveConfig(cluster_label="flyte"),
        query_template="""
            set engine=tez;
            insert overwrite directory '{{ .rawOutputDataPrefix }}' stored as parquet  -- will be unique per retry
            select *
            from blah
            where ds = '{{ .Inputs.ds }}' and uri = '{{ .inputs.my_schema }}'
        """,
        # the schema literal's backend uri will be equal to the value of .raw_output_data
        output_schema_type=FlyteSchema,
    )

    @workflow
    def my_wf(in_schema: FlyteSchema, ds: str) -> FlyteSchema:
        return hive_task(my_schema=in_schema, ds=ds)

    default_img = Image(name="default", fqn="test", tag="tag")
    serialization_settings = SerializationSettings(
        project="proj",
        domain="dom",
        version="123",
        image_config=ImageConfig(default_image=default_img, images=[default_img]),
        env={},
    )
    sdk_task = get_serializable(serialization_settings, hive_task)
    assert "{{ .rawOutputDataPrefix" in sdk_task.custom["query"]["query"]
    assert "insert overwrite directory" in sdk_task.custom["query"]["query"]
    assert len(sdk_task.interface.inputs) == 2
    assert len(sdk_task.interface.outputs) == 1

    sdk_wf = get_serializable(serialization_settings, my_wf)
    assert sdk_wf.interface.outputs["o0"].type.schema is not None
    assert sdk_wf.outputs[0].var == "o0"
    assert sdk_wf.outputs[0].binding.promise.node_id == "n0"
    assert sdk_wf.outputs[0].binding.promise.var == "results"


def test_local_exec():
    hive_task = HiveTask(
        name="flytekit.demo.hive_task.hivequery1",
        inputs={},
        config=HiveConfig(cluster_label="flyte"),
        query_template="""
            set engine=tez;
            insert overwrite directory '{{ .raw_output_data }}' stored as parquet  -- will be unique per retry
            select *
            from blah
            where ds = '{{ .Inputs.ds }}' and uri = '{{ .inputs.my_schema }}'
        """,
        output_schema_type=FlyteSchema,
    )

    assert len(hive_task.interface.inputs) == 0
    assert len(hive_task.interface.outputs) == 1

    # will not run locally
    with pytest.raises(Exception):
        hive_task()

    my_demo_output = pandas.DataFrame(data={"x": [1, 2], "y": ["3", "4"]})

    @workflow
    def my_wf() -> FlyteSchema:
        return hive_task()

    with task_mock(hive_task) as mock:
        mock.return_value = my_demo_output
        x = my_wf()
        df = x.open().all()
        y = df == my_demo_output
        assert y.all().all()


def test_query_no_inputs_or_outputs():
    hive_task = HiveTask(
        name="flytekit.demo.hive_task.hivequery1",
        inputs={},
        task_config=HiveConfig(cluster_label="flyte"),
        query_template="""
            insert into extant_table (1, 'two')
        """,
        output_schema_type=None,
    )

    @workflow
    def my_wf():
        hive_task()

    default_img = Image(name="default", fqn="test", tag="tag")
    serialization_settings = SerializationSettings(
        project="proj",
        domain="dom",
        version="123",
        image_config=ImageConfig(default_image=default_img, images=[default_img]),
        env={},
    )
    sdk_task = get_serializable(serialization_settings, hive_task)
    assert len(sdk_task.interface.inputs) == 0
    assert len(sdk_task.interface.outputs) == 0

    get_serializable(serialization_settings, my_wf)


def test_hive_select():
    hive_select = HiveSelectTask(
        name="flytekit.demo.hive_task.hivequery1",
        inputs={},
        task_config=HiveConfig(cluster_label="flyte"),
        select_query="select 1, 2, 3",
        output_schema_type=FlyteSchema,
    )

    sql = hive_select.get_query()
    assert "{{ .PerRetryUniqueKey }}_tmp" in sql
