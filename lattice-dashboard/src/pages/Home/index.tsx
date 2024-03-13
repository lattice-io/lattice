import { PageContainer } from "@ant-design/pro-layout";
import { Card, Steps } from "antd";

import ReactMarkdown from "react-markdown";
import { stepOne, stepTwo, stepThree } from "./markdown";
import "./index.less";

const latticeSteps = [
  {
    title: "Step 1",
    content: (
      <div style={{ marginLeft: "20px", marginTop: "-20px" }}>
        <ReactMarkdown children={stepOne} />
        <img
          style={{ width: "80%", marginLeft: "15%", marginTop: "40px" }}
          src="https://s2.loli.net/2023/02/09/wrgJaQCDGmxPScI.png"
        />
      </div>
    ),
  },
  {
    title: "Step 2",
    content: (
      <div style={{ marginLeft: "20px", marginTop: "-20px" }}>
        <ReactMarkdown children={stepTwo} />
        <img
          style={{ width: "80%", marginLeft: "15%", marginTop: "40px" }}
          src="https://s2.loli.net/2023/02/09/wrgJaQCDGmxPScI.png"
        />
      </div>
    ),
  },
  {
    title: "Step 3",
    content: (
      <div style={{ marginLeft: "20px", marginTop: "-20px" }}>
        <ReactMarkdown children={stepThree} />
        <img
          style={{ width: "80%", marginLeft: "15%", marginTop: "40px" }}
          src="https://s2.loli.net/2023/02/09/wrgJaQCDGmxPScI.png"
        />
      </div>
    ),
  },
];

// React Layouts.
export default function Home() {
  const [currentStep, setCurrentStep] = useState(0);

  const stepItems = latticeSteps.map((item) => ({
    key: item.title,
    title: item.title,
    content: item.content,
  }));

  const onStepChange = (value: number) => {
    setCurrentStep(value);
  };

  return (
    <PageContainer>
      <Card>
        <p className="title">Quick Start</p>
        <div
          style={{ display: "flex", flexDirection: "row", marginTop: "25px" }}
        >
          <Steps
            style={{ height: "30rem", width: "16%", marginLeft: "10px" }}
            direction="vertical"
            onChange={onStepChange}
            current={currentStep}
            items={stepItems}
          />
          <div style={{ marginTop: "20px", width: "70%" }}>
            {stepItems[currentStep].content}
          </div>
        </div>
      </Card>
    </PageContainer>
  );
}
