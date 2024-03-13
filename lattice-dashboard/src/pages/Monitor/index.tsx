import type { ColumnsType } from 'antd/es/table'
import { QuestionCircleOutlined, FileSearchOutlined, UploadOutlined } from '@ant-design/icons'
import { PageContainer } from '@ant-design/pro-layout'
import type { ProColumns } from '@ant-design/pro-components';
import { ProDescriptions, ProTable } from '@ant-design/pro-components';
import { Avatar, Card, Button, Form, Modal, Input, Table, Tooltip, Tag, Upload, Spin, Switch, Popconfirm, Space, Alert, message } from 'antd'
import axios from 'axios';
import type { UploadProps } from 'antd';

import './index.less'

import { v4 as uuidv4 } from 'uuid'
import { extend } from 'umi-request'
import { getBackendURL, getMonitorURL, colors } from '../../../config/apis'
import useIntervalAsync from './update'
import TimeSeriesChart, {
  WorkerData,
  WorkerNum,
} from '@/components/TimeSeriesChart'
import StaticBlockChart, {
  StaticWorkerData,
  StaticColorData
} from '@/components/StaticBlockChart'
import { ExampleJobType, ExampleData } from './example'
import { render } from 'react-dom'
import exp from 'constants';

const request = extend({
  prefix: getBackendURL(),
  headers: {
    'Content-Type': 'application/json',
  },
})

export enum JobStatusType {
  Running = 'Running',
  Completed = 'Completed',
  Waiting = 'Waiting',
  Initializing = 'Initializing',
  Cancelled = 'Cancelled',
}

export interface JobType {
  key: string
  name: string
  experiment: string
  priority: number
  job_size: number
  user: string
  status: JobStatusType
  start_time: string
  running_time: string
  download_url: string
  size_history: WorkerNum[]
  gpus: number
  cpus: number
  memory: number
  running_size: number
  namespace: string
}

export interface PlacementType {
  job: string[]
}

export default function Monitor() {
  const [clusterSize, setclusterSize] = useState('')
  const [epochs, setEpochs] = useState('')
  const [isLoadingJobs, setLoadingJobs] = useState(false)
  const [jobsData, setJobsData] = useState<JobType[]>([])
  const [isSubmitting, setSubmitting] = useState(false)
  const [isSizingCluster, setClusterSize] = useState(false)
  const [jobWorkerData, setJobWorkerData] = useState<WorkerData[]>([])
  const [staticWorkerData, setStaticJobWorkerData] = useState<
    StaticWorkerData[]
  >([])
  const [nodeMap, setNodeMap] = useState<Map<number, string>>(new Map())
  const [jobColor, setJobColor] = useState<Map<string, string>>(new Map())
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isCustomJobSubmitting, setCustomJobSubmitting] = useState(false)
  const [checked, setChecked] = useState(true);
  const [jobLog, setJobLog] = useState<Map<string, string[]>>(new Map())
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set())

  const [newJobInfo] = Form.useForm()
  const [newClusterInfo] = Form.useForm()

  const updateState = useCallback(async () => {
    await getJobs()
    await getLogs()
  }, [])

  const updateJobs = useIntervalAsync(updateState, 2000)

  const list: any[] = []

  useEffect(() => {
    ; (async function () {
      updateJobs
    })()
  }, [])

  useEffect(() => {
    // console.log(jobWorkerData)
  }, [jobWorkerData])

  // scaleClusterSubmit: submit the customized cluster size to api server.
  const scaleClusterSubmit = (desiredSize: number) => () => {
    setClusterSize(true)
    request
      .post('/cluster', {
        data: { 'desired_size': desiredSize }
      })
      .then(function (response) {
        message.success('Successfully submit a new cluster size! Cluster size: ' + desiredSize)
        console.log(response)
        setClusterSize(false)
        newClusterInfo.resetFields()
      })
      .catch(function (error) {
        console.log(error)
        message.error('Error! Error message: ' + error)
        setClusterSize(false)
        newClusterInfo.resetFields()
      })
  }

  const props: UploadProps = {
    name: 'file',
    accept: '.zip,.tar',
    action: 'http://localhost:8080/api/datasets',
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onChange(info) {
      if (info.file.status !== 'uploading') {
        console.log(info.file, info.fileList);
      }
      if (info.file.status === 'done') {
        message.success(`${info.file.name} file uploaded successfully`);
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} file upload failed.`);
      }
    },
    progress: {
      strokeColor: {
        '0%': '#108ee9',
        '100%': '#87d068',
      },
      strokeWidth: 3,
      format: (percent) => percent && `${parseFloat(percent.toFixed(2))}%`,
    },
    customRequest: (info: any) => {
      const data = new FormData()
      data.append('file', info.file)
      const config = {
        "headers": {
          "content-type": 'multipart/form-data; boundary=----WebKitFormBoundaryqTqJIxvkWFYqvP5s'
        }
      }
      axios.post(info.action, data, config).then((res: any) => {
        info.onSuccess(res.data, info.file)
      }).catch((err: Error) => {
        console.log(err)
      })
    },
  };

  // Columns for example jobs.
  const exampleColumns: ColumnsType<ExampleJobType> = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text) => <a>{text}</a>,
    },
    {
      title: 'Model',
      dataIndex: 'model',
      key: 'model',
    },
    // {
    //   title: 'Stroage Type',
    //   dataIndex: 'storage',
    //   key: 'storage',
    // },
    {
      title: 'Dataset',
      dataIndex: 'dataset',
      key: 'dataset',
    },
    {
      title: 'Tags',
      key: 'tags',
      dataIndex: 'tags',
      render: (_, { tags }) => (
        <>
          {tags.map((tag) => {
            let color = tag.length > 5 ? 'geekblue' : 'green'
            if (tag === 'Classification') {
              color = 'volcano'
            } else if (tag === 'PyTorch') {
              color = 'red'
            }
            return (
              <Tag color={color} key={tag}>
                {tag.toUpperCase()}
              </Tag>
            )
          })}
        </>
      ),
    },
    {
      title: 'Epoch',
      dataIndex: 'epochs',
      key: 'epochs',
      render: () => (
        <Form.Item
          name='epochs'
          style={{ marginBottom: '0px', width: '43%' }}
          rules={[
            {
              required: true,
              message: 'Please input a integer',
            },
          ]}
        >
          <Input size='middle' onChange={event => setEpochs(event.target.value)} placeholder='Please input a integer' />
        </Form.Item>
      ),
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Space size='middle'>
          <Popconfirm
            title='Are you sure to submit this job?'
            onConfirm={onJobSubmit(record, parseInt(epochs))}
            okText='Yes'
            cancelText='No'
          >
            <a>Submit</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // columns for ML job table.
  const jobColumns: ProColumns<JobType>[] = [
    {
      title: 'Job Name',
      dataIndex: 'name',
      key: 'name',
      render: (text, _, index) => (
        <div>
          <Avatar style={{ backgroundColor: colors[index] }} shape='circle' size={12} />
          {' '}
          {text}
        </div>
      ),
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      key: 'priority',
      render: (_, record) => {
        if (record.status === 'Completed' || record.status === 'Cancelled') {
          return <p>N.A</p>
        } else {
          return (
            <div>
              {record.priority === 0 ? 'Low' : 'High'}
              <Popconfirm
                title={
                  'Are you sure to renice this job to ' +
                  (record.priority === 0 ? 'high' : 'low') +
                  ' priority?'
                }
                onConfirm={updateJobPriority(record.name, record.priority)}
                okText='Yes'
                cancelText='No'
              >
                <a style={{ marginLeft: '5px' }}>[renice]</a>
              </Popconfirm>
            </div>
          )
        }
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      filters: [
        {
          text: 'Running',
          value: 'Running',
        },
        {
          text: 'Waiting',
          value: 'Waiting',
        },
        {
          text: 'Cancelled',
          value: 'Cancelled',
        },
        {
          text: 'Completed',
          value: 'Completed',
        },
      ],
      onFilter: (value, record) => record.status === value,
      render: (status) => {
        if (status === 'Running') {
          return <Tag color='blue'>Running</Tag>
        } else if (status === 'Waiting') {
          return <Tag color='grey'>Waiting</Tag>
        } else if (status === 'Cancelled') {
          return <Tag color='red'>Cancelled</Tag>
        } else if (status === 'Completed') {
          return <Tag color='green'>Completed</Tag>
        } else if (status === '') {
          return <Tag color='yellow'>Initializing</Tag>
        }
      },
    },
    {
      title: 'Start Time',
      dataIndex: 'start_time',
      key: 'start_time',
    },
    {
      title: 'Running Time',
      dataIndex: 'running_time',
      key: 'running_time',
    },
    {
      title: 'Actual Worker(s)',
      dataIndex: 'running_size',
      key: 'running_size',
    },
    {
      title: 'Expected Worker(s)',
      dataIndex: 'job_size',
      key: 'job_size',
    },
    {
      title: 'Action',
      key: 'action',
      render: (_, record) => (
        <Space size='middle'>
          {record.status === 'Completed' ? (
            <a href={record.download_url}>Download</a>
          ) : (
            <a style={{ color: 'grey' }}>Download</a>
          )}
          <Popconfirm
            title='Are you sure to delete this job?'
            onConfirm={onJobDelete(record.name)}
            okText='Yes'
            cancelText='No'
          >
            {/* TODO: onDownload model report. */}
            <a style={{ color: 'red' }}>Delete</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Using template job configuration to update the online jobs.
  const updateJobPriority = (jobName: string, priority: number) => () => {
    let targetPriority: number
    if (priority > 0) {
      targetPriority = 0
    } else {
      targetPriority = 1
    }

    request
      .patch('/job', {
        data: {
          apiVersion: 'breezeml.ai/v1',
          kind: 'TrainingJob',
          metadata: {
            name: jobName,
            namespace: 'lattice',
          },
          spec: {
            priority: targetPriority,
          },
        },
      })
      .then(function (response) {
        try {
          getJobs()
          console.log(response)
        } catch (error) {
          console.log(error)
        }
      })
      .catch(function (error) {
        console.log(error)
      })
  }

  // get jobs API.
  const getJobs = async () => {
    request
      .get('/job')
      .then(function (response) {
        try {
          setJobsData(response.jobs)
          genWorkerSeriesData(response.jobs)
          genWorkersData(response.placement)
        } catch (error) {
          console.log(error)
        }
      })
      .catch(function (error) {
        console.log(error)
      })
  }

  // getNamespacedName: get the namespaced name of a job.
  const getNamespacedName = (namespace: string, name: string) => {
    return namespace + ' ' + name
  }

  // setLog: set the log for a job.
  const setLog = (namespace: string, name: string, logs: any) => {
    const log = new Map(jobLog)
    if (logs != null) {
      log.set(getNamespacedName(namespace, name), logs.map((l: any) => {
        return '<' + l.pod + '> ' + l.log
      }))
    }
    setJobLog(log)
  }

  // get logs API.
  const getLogs = async () => {
    for (const jobNamespacedName of expandedJobs) {
      // split the namespaced name
      const splittedName = jobNamespacedName.split(' ', 2)
      const jobNamespace = splittedName[0]
      const jobName = splittedName[1]
      request
        .get('/log/' + jobNamespace + '/' + jobName)
        .then(function (response) {
          setLog(jobNamespace, jobName, response.log)
        })
        .catch(function (error) {
          console.log(error)
        })
    }
  }

  // onJobDelete: delete a cluster job.
  const onJobDelete = (jobName: string) => () => {
    request
      .delete('/job?name=' + jobName)
      .then(function (_) {
        getJobs()
        setLoadingJobs(false)
      })
      .catch(function (error) {
        console.log(error)
        setLoadingJobs(false)
      })
  }

  const onJobSubmit = (data: ExampleJobType, epochsNum?: number) => () => {
    setSubmitting(true)
    // Add random ID after creating a new job.
    if (data.config.metadata.name.split('-').pop() === '') {
      data.config.metadata.name += uuidv4().substring(0, 8)
    } else {
      data.config.metadata.name =
        data.config.metadata.name.slice(0, -8) + uuidv4().substring(0, 8)
    }
    data.config.epochs = epochsNum

    // Send request.
    request
      .post('/job/' + data.submiturl, {
        data: data.config,
      })
      .then(function (response) {
        getJobs()
        message.success('Successfully submit a new job! Job name: ' + data.name)
        console.log(response)
        setSubmitting(false)
      })
      .catch(function (error) {
        console.log(error)
        message.error('Error! Error message: ' + error)
        setSubmitting(false)
      })
  }

  // genWorkerSeriesData: generate the timeseries data for job workers.
  const genWorkerSeriesData = (jobs: JobType[]) => {
    const jobWorkerList = [] as WorkerData[]
    const staticJobWorkerList = [] as StaticWorkerData[]
    const staticJobColorList = [] as StaticColorData[]

    //record the color for each job
    const staticJobWorkerMap = new Map()

    if (jobs != null) {
      jobs.forEach((job, index) => {
        // generate the time-eries data of runnning workers.
        jobWorkerList.push({
          name: job.name,
          data: job.size_history.map((history) => {
            return { x: history.time * 1000, y: history.value }
          }),
        })

        // generate the static chart data of running worker.
        if (job.status === 'Running') {
          staticJobWorkerList.push({
            x: job.key.substring(0, 8),
            y: job.job_size,
          })
        }

        // generate the static map data of running worker.
        staticJobColorList.push({
          name: job.key.substring(0, 8),
          color: colors[index]
        })
      })

      setJobWorkerData(jobWorkerList)
      setStaticJobWorkerData(staticJobWorkerList)

      for (const worker in staticJobColorList) {
        staticJobWorkerMap.set(staticJobColorList[worker].name, staticJobColorList[worker].color)
      }
      setJobColor(staticJobWorkerMap)
    }
  }

  const genWorkersData = (placements: string[]) => {
    const freqMap = new Map()

    let j = 0
    if (placements != null) {
      for (const i in placements) {
        freqMap.set(j, String(placements[i]).substring(0, 8));
        j++
      }
    }

    setNodeMap(freqMap)
  }

  const setAvatarNum = () => {
    for (const val of nodeMap.values()) {
      if (jobColor.has(val)) {
        list.push(<Avatar style={{ backgroundColor: jobColor.get(val) }} shape='square' size='small' />)
      } else {
        list.push(<Avatar style={{ backgroundColor: 'grey' }} shape='square' size='small' />)
      }
    }

    return (
      <Spin spinning={isLoadingJobs}>
        <div>
          {list}
        </div>
      </Spin>
    )
  }

  const showModal = () => {
    setIsModalOpen(true);
  };

  const handleCancel = () => {
    setIsModalOpen(false);
    newJobInfo.resetFields()
    setChecked(false)
  };

  // onNewJobSubmitted: callback for creating a new ML job.
  const onNewJobSubmitted = (data: any) => {
    ; (async function () {
      setIsModalOpen(false)
      setCustomJobSubmitting(true)
      request
        .post('/job', {
          data: {
            apiVersion: 'breezeml.ai/v1',
            kind: 'TrainingJob',
            metadata: {
              name: 'lattice-' + data.name + '-' + uuidv4().substring(0, 8),
              namespace: 'lattice',
            },
            spec: {
              runPolicy: {
                cleanPodPolicy: 'None',
              },
              replicaSpecs: {
                template: {
                  spec: {
                    containers: [
                      {
                        name: 'trainingjob',
                        image: String(data.docker_img),
                        imagePullPolicy: 'Always',
                        command: typeof (data.commands) === 'string' ? data.commands.split(' ') : null,
                        args: typeof (data.args) === 'string' ? data.args.split(' ') : null,
                        resources: {
                          requests: {
                            'nvidia.com/gpu': 1,
                          },
                          limits: {
                            'nvidia.com/gpu': 1,
                          },
                        },
                      },
                    ],
                  },
                },
              },
              minSize: Number(data.min_worker),
              maxSize: Number(data.max_worker),
              injectLattice: Boolean(data.injectLattice),
            },
          },
        })
        .then(function (response) {
          console.log(response)
          setCustomJobSubmitting(false)
          message.success('Successfully submit a new customized job!')
          newJobInfo.resetFields()
          setChecked(false)
        })
        .catch(function (error) {
          console.log(error)
          setCustomJobSubmitting(false)
          message.error(error)
          newJobInfo.resetFields()
          setChecked(false)
        })
    })()
  }

  const renderJobLog = (record: any) => {
    return (
      <ProDescriptions style={{ height: '200px', overflow: 'auto' }}>
        <ProDescriptions.Item
          label="logs"
          valueType="code"
        >
          {jobLog.get(getNamespacedName(record.namespace, record.name))}
        </ProDescriptions.Item>
      </ProDescriptions>
    )
  }

  return (
    <PageContainer>
      <Card>
        <p className='card_title'>Customization</p>
        <Spin tip='Submitting' size='large' spinning={isSizingCluster}>
          <Alert
            style={{ marginBottom: '1rem' }}
            message='You can customize your training job specifications here.'
            type='info'
            closable
          />
          <Form
            layout='inline'
            form={newClusterInfo}
            name='control-hooks'
            onFinish={scaleClusterSubmit(parseInt(clusterSize))}
          >
            <Form.Item
              rules={[
                {
                  required: true,
                  message: 'Please input a cluster size (maximum 12).',
                },
              ]}
              label='Cluster Size (default 0):'
              name='size'
              style={{ width: '38%' }}
            >
              <Input onChange={event => setclusterSize(event.target.value)} placeholder='Please input a integer (maximum 12)' />
            </Form.Item>
            <Button
              type='primary'
              onClick={newClusterInfo.submit}
            >
              Submit
            </Button>
          </Form>
        </Spin>
        <div style={{ marginLeft: '10px', marginTop: '20px' }}>
          <Form
            layout='inline'
            name='control-hooks'
          >
            <Form.Item
              name="upload"
              label="Dataset (a .zip/.tar file) :"
            >
              <Upload {...props}>
                <Button icon={<UploadOutlined />}>Click to Upload</Button>
              </Upload>
            </Form.Item>
          </Form>
        </div>
      </Card>
      <Card style={{ marginTop: '1rem' }}>
        <p className='card_title'>Training Job Templates</p>
        <Spin tip='Submitting' size='large' spinning={isSubmitting}>
          <Alert
            message='You can get started by submitting following example jobs.'
            type='info'
            closable
          />
          <Table
            style={{ marginTop: '10px' }}
            columns={exampleColumns}
            dataSource={ExampleData}
          />
          <Alert
            style={{ marginBottom: '1rem' }}
            message='You can also create a job by clicking below.'
            type='info'
            closable
          />
        </Spin>
        <Button
          type='link'
          onClick={showModal}
        >
          Create Your Own Job
        </Button>
        <Modal
          title="Please specify the training job configuration:"
          open={isModalOpen}
          okText="Submit"
          cancelText="Cancel"
          onOk={() => { newJobInfo.submit() }}
          onCancel={handleCancel}
          width={650}
        >
          <Spin tip='Loading' size='large' spinning={isCustomJobSubmitting}>
            <Form
              layout='vertical'
              form={newJobInfo}
              name='control-hooks'
              onFinish={onNewJobSubmitted}
            >
              <Form.Item
                rules={[
                  {
                    required: true,
                    message: 'Please input a job name.',
                  },
                ]}
                label='Job Name:'
                name='name'
                style={{ width: '65%' }}
              >
                <Input />
              </Form.Item>
              <Form.Item
                rules={[
                  {
                    required: true,
                    message:
                      'Please input a Docker image that runs your program.',
                  },
                ]}
                label='Docker Image:'
                name='docker_img'
                style={{ width: '65%' }}
              >
                <Input placeholder='A docker image contains your ML script.' />
              </Form.Item>
              <Form.Item
                label='Command(s):'
                name='commands'
                style={{ width: '65%' }}
              >
                <Input placeholder='Please use space to split docker container entrypoint commands.' />
              </Form.Item>
              <div style={{ display: 'flex', flexDirection: 'row' }}>
                <Form.Item
                  rules={[
                    {
                      required: true,
                      message: 'Please input a min number.',
                    },
                  ]}
                  label='Min Worker(s):'
                  name='min_worker'
                  style={{ width: '30%', marginRight: '5%' }}
                >
                  <Input placeholder='minimum worker number' />
                </Form.Item>
                <Form.Item
                  rules={[
                    {
                      required: true,
                      message: 'Please input a max number.',
                    },
                  ]}
                  label='Max Worker(s):'
                  name='max_worker'
                  style={{ width: '30%' }}
                >
                  <Input placeholder='maximum worker number' />
                </Form.Item>
              </div>
              <Form.Item
                label='Arg(s):'
                name='args'
                style={{ width: '65%' }}
              >
                <Input placeholder='Please use space to split arguments.' />
              </Form.Item>
              <Form.Item
                label={
                  <span>
                    Enable Elasticity&nbsp;
                    <Tooltip
                      placement="rightTop"
                      title="Enabling elasticity(PyTorch >= 1.10) will allow Lattice to 
                              make sure your job can be resized between min and max number 
                              of workers without any interruptions or data loss" >
                      <QuestionCircleOutlined />
                    </Tooltip>
                  </span>
                }
                name='injectLattice'
                valuePropName='checked'
              >
                <Switch checked={checked} onChange={setChecked} />
              </Form.Item>
            </Form>
          </Spin>
        </Modal>
      </Card>
      <Card style={{ marginTop: '1rem' }}>
        <p className='card_title'>Job Monitor</p>
        <Alert
          style={{ marginBottom: '1rem' }}
          message='You can acquire all the jobs information here.'
          type='info'
          closable
        />
        <div style={{ display: 'flex', flexDirection: 'row' }}>
          <div style={{ width: '70%' }}>
            <TimeSeriesChart series={jobWorkerData} />
          </div>
        </div>
        Workers:{setAvatarNum()}
        <Spin spinning={isLoadingJobs}>
          <ProTable
            tableStyle={{ marginTop: '1rem', marginLeft: '-1.5rem' }}
            columns={jobColumns}
            locale={{ emptyText: 'There is no data' }}
            dataSource={jobsData}
            search={false}
            options={false}
            expandable={{
              expandedRowRender: renderJobLog,
              onExpand: (expanded, record) => {
                if (expanded) {
                  if (!expandedJobs.has(getNamespacedName(record.namespace, record.name))) {
                    setExpandedJobs(expandedJobs.add(getNamespacedName(record.namespace, record.name)))
                  }
                } else {
                  if (expandedJobs.has(getNamespacedName(record.namespace, record.name))) {
                    expandedJobs.delete(getNamespacedName(record.namespace, record.name))
                    setExpandedJobs(expandedJobs)
                  }
                }
              },
              expandIcon: ({ expanded, onExpand, record }) =>
                <FileSearchOutlined onClick={e => onExpand(record, e)} />
            }}
          />
        </Spin>
      </Card>
    </PageContainer>
  )
}
