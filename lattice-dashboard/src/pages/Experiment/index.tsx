import { PageContainer } from '@ant-design/pro-layout'
import { Card, Button, Form, Collapse, Input, Spin, message } from 'antd'
import { CaretRightOutlined } from '@ant-design/icons'

import { v4 as uuidv4 } from 'uuid'
import { extend } from 'umi-request'
import { getBackendURL } from '../../../config/apis'

import styles from './index.module.less'
import './index.less'

const { Panel } = Collapse
const request = extend({
  prefix: getBackendURL(),
  headers: {
    'Content-Type': 'application/json',
  },
})

export default function Experiment() {
  const [newJobInfo] = Form.useForm()
  const [isSubmitting, setSubmitting] = useState(false)

  // onNewJobSubmitted: callback for creating a new ML job.
  const onNewJobSubmitted = (data: any) => {
    ;(async function () {
      setSubmitting(true)
      console.log(data)
      request
        .post('/jobs', {
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
              minSize: Number(data.min_worker),
              maxSize: Number(data.max_worker),

              // NOTE: We only inject lattice agent and addon when min != max, i.e., the job may be scaled
              injectLattice: data.min_worker === data.max_worker ? false : true,

              // NOTE: Force to run on GPU instance
              replicaSpecs: {
                template: {
                  spec: {
                    containers: [
                      {
                        name: 'trainingjob',
                        image: String(data.docker_img),
                        imagePullPolicy: 'Always',
                        command: data.entrypoint.split(' '),
                        resources: {
                          limits: {
                            'nvidia.com/gpu': 1,
                          },
                        },
                      },
                    ],
                  },
                },
              },
            },
          },
        })
        .then(function (response) {
          console.log(response)
          setSubmitting(false)
          message.success('Successfully submit a new job!')
        })
        .catch(function (error) {
          console.log(error)
          setSubmitting(false)
          message.error(error)
        })
    })()
  }

  return (
    <PageContainer>
      <Card>
        <p className='title'> Creating a training job</p>
        <Spin tip='Loading' size='large' spinning={isSubmitting}>
          <Form
            layout='vertical'
            form={newJobInfo}
            name='control-hooks'
            onFinish={onNewJobSubmitted}
          >
            <Collapse
              bordered={false}
              defaultActiveKey={['1']}
              expandIcon={({ isActive }) => (
                <CaretRightOutlined rotate={isActive ? 90 : 0} />
              )}
            >
              <Panel
                header='Generation Information'
                key='1'
                className={styles.panel}
              >
                <p>Specify the details about this training job</p>
                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item
                    rules={[
                      {
                        required: true,
                        message: 'Please input a job name.',
                      },
                    ]}
                    label='Job Name:'
                    name='name'
                    style={{ width: '40%' }}
                  >
                    <Input placeholder='Please input a job name.' />
                  </Form.Item>
                  {/* TODO: enable this feature. */}
                  <Form.Item
                    label='Priority:'
                    name='priority'
                    style={{ width: '40%', marginLeft: '1%' }}
                  >
                    <Input
                      disabled
                      placeholder='Please indicate a job priority.'
                    />
                  </Form.Item>
                  <a
                    style={{
                      height: '100px',
                      lineHeight: '90px',
                      textAlign: 'center',
                      marginLeft: '20px',
                    }}
                  >
                    Need higher priority?
                  </a>
                </div>

                <div style={{ display: 'flex', flexDirection: 'row' }}>
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
                    style={{ width: '40%' }}
                  >
                    <Input placeholder='The docker image contains your ML script.' />
                  </Form.Item>
                  <Form.Item
                    label='Entrypoint:'
                    name='entrypoint'
                    style={{ width: '40%', marginLeft: '1%' }}
                  >
                    <Input placeholder='Please docker container entrypoint command' />
                  </Form.Item>
                  <a
                    style={{
                      height: '100px',
                      lineHeight: '90px',
                      width: '10%',
                      marginLeft: '20px',
                    }}
                  >
                    Need help?
                  </a>
                </div>

                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item
                    rules={[
                      {
                        required: true,
                        message: 'Please input a min worker number',
                      },
                    ]}
                    label='Min Worker:'
                    initialValue='1'
                    name='min_worker'
                    style={{ width: '20%' }}
                  >
                    <Input placeholder='minimum worker number.' />
                  </Form.Item>
                  <Form.Item
                    rules={[
                      {
                        required: true,
                        message: 'Please input a max worker number',
                      },
                    ]}
                    label='Max Worker:'
                    initialValue='1'
                    name='max_worker'
                    style={{ width: '20%', marginLeft: '20px' }}
                  >
                    <Input placeholder='maximum worker number.' />
                  </Form.Item>
                </div>
              </Panel>
              <Panel
                header='Resource Settings'
                key='3'
                className={styles.panel}
              >
                <p>Specific your resources.</p>
                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item label='CPU:' name='cpus' style={{ width: '30%' }}>
                    <Input placeholder='Please indicate a CPU core number.' />
                  </Form.Item>
                  <Form.Item
                    label='GPU Number:'
                    name='gpus'
                    style={{ width: '30%', marginLeft: '20px' }}
                  >
                    <Input placeholder='Please indicate a GPU number.' />
                  </Form.Item>
                  <Form.Item
                    label='Memory:'
                    name='memory'
                    style={{ width: '30%', marginLeft: '20px' }}
                  >
                    <Input placeholder='Please indicate a memory size.' />
                  </Form.Item>
                </div>
              </Panel>
              <Panel header='Model Settings' key='2' className={styles.panel}>
                <p>Specific model hyperparameters</p>
                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item
                    label='Epoch:'
                    name='epoch'
                    style={{ width: '40%' }}
                  >
                    <Input placeholder='Please input a training epoch.' />
                  </Form.Item>
                  <Form.Item
                    label='Batch Size:'
                    name='batch_size'
                    style={{ width: '40%', marginLeft: '20px' }}
                  >
                    <Input placeholder='Please indicate a training data batch size.' />
                  </Form.Item>
                </div>
                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item
                    label='Learning Rate:'
                    name='learning_rate'
                    style={{ width: '40%' }}
                  >
                    <Input placeholder='Please input a training learning rate.' />
                  </Form.Item>
                  <Form.Item
                    label='Optimizer:'
                    name='optimizer'
                    style={{ width: '40%', marginLeft: '20px' }}
                  >
                    <Input placeholder='Please indicate a training optimizer.' />
                  </Form.Item>
                </div>
                <div style={{ display: 'flex', flexDirection: 'row' }}>
                  <Form.Item
                    label='Custom Parameters:'
                    name='custom_para'
                    style={{ width: '82%' }}
                  >
                    <Input placeholder='Please add parameters in key:value; mannner.' />
                  </Form.Item>
                </div>
              </Panel>
            </Collapse>
          </Form>
        </Spin>

        <div style={{ textAlign: 'right' }}>
          <Button
            type='primary'
            onClick={() => {
              newJobInfo.submit()
            }}
          >
            Submit
          </Button>
        </div>
      </Card>
    </PageContainer>
  )
}
